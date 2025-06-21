import os, datetime
from typing import Optional, Literal
import discord
from discord import app_commands
from discord.ui import View, button
from discord import ButtonStyle
from dotenv import load_dotenv
import config, lmsr, data, broadcasts


# Load .env
load_dotenv()
DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID", 0))
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
TOKEN = os.getenv("DISCORD_TOKEN")


# Bot subclass
class PredictionBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if DEV_GUILD_ID:
            guild = discord.Object(id=DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


# Instantiate the bot
bot = PredictionBot()


# Events
@bot.event
async def on_ready():
    # Initialize unified database
    await data.init_db()
    # Log in message
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")


# Confirmation view for /delete_market
class DeleteConfirmView(View):
    def __init__(self, market_id: str):
        # timeout=None → buttons never expire
        super().__init__(timeout=60)
        self.market_id = market_id

    @button(label="Confirm", style=ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button):
        if interaction.user.id != ADMIN_ID:
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        try:
            await data.delete_market(self.market_id)
            await interaction.response.edit_message(
                content=f"✅ Market `{self.market_id}` deleted.",
                view=None
            )
        except ValueError as e:
            await interaction.response.edit_message(
                content=f"❌ {e}", view=None
            )

    @button(label="Cancel", style=ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(
            content="❌ Deletion canceled", view=None
        )


# Confirmation view for /buy
class BuyConfirmView(View):
    def __init__(self, user_id, market_id, outcome, amount, shares, price):
        # Auto-timeout after 60s
        super().__init__(timeout=60)
        self.user_id   = user_id
        self.market_id = market_id
        self.outcome   = outcome
        self.amount    = amount
        self.shares    = shares
        self.price     = price
        self.message   = None  # Will hold the sent message

    # Timeout handler
    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(
                    content="❌ Buy order expired",
                    view=None
                )
            except:
                pass

    @button(label="Confirm", style=ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button):
        if str(interaction.user.id) != self.user_id:
            return await interaction.response.send_message("❌ Not your order", ephemeral=True)

    # Final price check before executing buy (in case another user traded in the meantime)
        markets = await data.load_markets()
        m = markets[self.market_id]
        qy, qn, b = m['shares']['YES'], m['shares']['NO'], m['b']
        # How many shares this amount would buy now
        new_shares = lmsr.calc_shares(self.amount, qy, qn, b, self.outcome)
        new_avg = self.amount / new_shares
        # Abort if average price changed
        if abs(new_avg - self.price) > 1e-6:
            return await interaction.response.edit_message(
                content=(
                    f"❌ Buy order failed. Price has moved from **${self.price:.4f}** to **${new_avg:.4f}**."
                ),
                view=None
            )

        # Update balances and portfolio
        await data.update_balance(self.user_id, -self.amount)
        await data.update_balance(config.POOL_ID, self.amount)
        await data.add_bet(self.user_id, self.market_id, self.outcome, self.shares, self.amount)

        # Update market shares
        markets = await data.load_markets()
        m = markets[self.market_id]
        m['shares'][self.outcome] += self.shares

        # Compute new LMSR marginal price
        qy, qn, b = m['shares']['YES'], m['shares']['NO'], m['b']
        implied_yes = lmsr.lmsr_price(qy, qn, b)

        # Record new implied odds, timestamp, and add to total volume traded
        m['implied_odds'] = implied_yes
        m["last_trade"] = datetime.datetime.now(datetime.UTC).isoformat()
        m["volume_traded"] = m.get("volume_traded", 0) + abs(self.amount)
        await data.save_markets(markets)
       
        # Log to trades.db
        balance = await data.get_balance(self.user_id)
        await data.log_trade(
            user_id   = self.user_id,
            market_id = self.market_id,
            outcome   = self.outcome,
            shares    = self.shares,   # positive for buy
            amount    = self.amount,   # positive dollars spent
            price     = self.price,
            balance   = balance
        )
       
        # Broadcast publicly
        await broadcasts.broadcast_trade(
            client       = interaction.client,
            market_id    = self.market_id,
            market_name  = m['question'],
            side         = "BUY",
            outcome      = self.outcome,
            shares       = self.shares,
            amount       = self.amount,
            implied_odds = implied_yes
        )

        # Compute profit
        profit_after_fee = (self.shares - self.amount) * (1 - config.REDEEM_FEE)
        pct = (profit_after_fee / self.amount) * 100 if self.amount else 0

        # Confirm to user
        await interaction.response.edit_message(
            content=(
                f"✅ Bought **{self.shares:.4f}** `{self.outcome}` shares in `{self.market_id}`\n"
                f"Average price: **${self.price:.4f}**/share\n"
                f"Spent: **${self.amount:.2f}**\n"
                f"Potential profit (after {config.REDEEM_FEE*100}% fee): **${profit_after_fee:.2f}** ({pct:+.1f}%)\n"
                f"New balance: **${await data.get_balance(self.user_id):.2f}**"
            ),
            view=None
        )
        
    @button(label="Cancel", style=ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(
            content="❌ Buy order canceled", view=None
        )


# Confirmation view for /sell
class SellConfirmView(View):
    def __init__(self, user_id: str, market_id: str, outcome: str, percent: int, shares: float, price: float):
        super().__init__(timeout=60)
        self.user_id    = user_id
        self.market_id  = market_id
        self.outcome    = outcome
        self.percent    = percent
        self.shares     = shares
        self.price      = price      # Avg price calculated at command time
        self.message    = None

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(content="❌ Sell order expired", view=None)
            except:
                pass

    @button(label="Confirm", style=ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button):
        # Only original user can confirm
        if str(interaction.user.id) != self.user_id:
            return await interaction.response.send_message("❌ Not your order.", ephemeral=True)

        # Final price check
        markets = await data.load_markets()
        m = markets[self.market_id]
        qy, qn, b = m['shares']['YES'], m['shares']['NO'], m['b']
        current_cost = lmsr.lmsr_cost(qy, qn, b)
        if self.outcome == "YES":
            new_cost = lmsr.lmsr_cost(qy - self.shares, qn, b)
        else:
            new_cost = lmsr.lmsr_cost(qy, qn - self.shares, b)
        new_amount = current_cost - new_cost
        new_avg = new_amount / self.shares
        if abs(new_avg - self.price) > 1e-6:
            return await interaction.response.edit_message(
                content=(
                    f"❌ Sell order failed. Price has moved from **${self.price:.4f}** to **${new_avg:.4f}**."
                ),
                view=None
            )

        # Execute sell: debit pool, credit user
        await data.update_balance(self.user_id, new_amount)
        await data.update_balance(config.POOL_ID, -new_amount)

        # Update user's position
        await data.add_bet(self.user_id, self.market_id, self.outcome, -self.shares, -new_amount)

        # Update market data
        m['shares'][self.outcome] -= self.shares
        implied_yes = lmsr.lmsr_price(m['shares']['YES'], m['shares']['NO'], b)
        m['implied_odds']  = implied_yes
        m['last_trade']    = datetime.datetime.now(datetime.timezone.utc).isoformat()
        m['volume_traded'] = m.get('volume_traded', 0) + abs(new_amount)
        await data.save_markets(markets)

        # Log the trade (negative shares & negative amount)
        balance = await data.get_balance(self.user_id)
        await data.log_trade(
            user_id   = self.user_id,
            market_id = self.market_id,
            outcome   = self.outcome,
            shares    = -self.shares,
            amount    = -new_amount,
            price     = self.price,
            balance   = balance
        )

        # Broadcast publicly
        await broadcasts.broadcast_trade(
            client       = interaction.client,
            market_id    = self.market_id,
            market_name  = m['question'],
            side         = "SELL",
            outcome      = self.outcome,
            shares       = self.shares,
            amount       = new_amount,
            implied_odds = implied_yes
        )

        # Confirm to user
        await interaction.response.edit_message(
            content=(
                f"✅ Sold **{self.shares:.4f}** `{self.outcome}` shares in `{self.market_id}`\n"
                f"Average price: **${self.price:.4f}**/share\n"
                f"Received: **${new_amount:.2f}**\n"
                f"New balance: **${balance:.2f}**"
            ),
            view=None
        )

    @button(label="Cancel", style=ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(content="❌ Sell order canceled", view=None)


# Confirmation view for /send
class SendConfirmView(View):
    def __init__(self, sender_id: str, recipient_id: str, amount: float):
        super().__init__(timeout=60)
        self.sender_id = sender_id
        self.recipient_id = recipient_id
        self.amount = amount

    @button(label="Confirm", style=ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button):
        # Only the original sender can confirm
        if str(interaction.user.id) != self.sender_id:
            return await interaction.response.send_message(
                "❌ You are not authorized to confirm this transfer.",
                ephemeral=True
            )

        # Fetch current balances one last time
        sender_bal = await data.get_balance(self.sender_id)
        if self.amount > sender_bal:
            # If somehow balance changed since initial check
            return await interaction.response.edit_message(
                content=f"❌ Insufficient funds. Your current balance is ${sender_bal:.2f}.",
                view=None
            )

        # Debit the sender
        await data.update_balance(self.sender_id, -self.amount)
        # Credit the recipient
        await data.update_balance(self.recipient_id, self.amount)
        # Log the transfer once (from_user -> to_user)
        new_sender_bal = await data.get_balance(self.sender_id)
        await data.log_transfer(
            type="transfer",
            from_user=self.sender_id,
            to_user=self.recipient_id,
            amount=self.amount,
            balance=new_sender_bal
        )

        # Acknowledge back to the sender
        await interaction.response.edit_message(
            content=(
                f"✅ **Transfer complete!**\n"
                f"You sent **${self.amount:.2f}** to <@{self.recipient_id}>.\n"
                f"Your new balance is **${new_sender_bal:.2f}**."
            ),
            view=None
        )

    @button(label="Cancel", style=ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button):
        # Anyone can cancel, but the message becomes “canceled”
        await interaction.response.edit_message(
            content="❌ Transfer canceled.",
            view=None
        )


# Slash commands

# /create_market (admin only)
@bot.tree.command(
    name="create_market",
    description="Admin: create a YES/NO market with ID, question, details, subject, and b-parameter"
)
@app_commands.describe(
    id="Unique ID for this market",
    question="The question for this market",
    details="Details and conditions for the market",
    subject="Optional subject ID (to block self-bets)",
    b=f"LMSR b-parameter (liquidity), default={config.DEFAULT_B}"
)
async def create_market(
    interaction: discord.Interaction,
    id: str,
    question: str,
    details: Optional[str] = None,
    subject: Optional[str] = None,
    b: float = config.DEFAULT_B
):
    # Admin guard
    if interaction.user.id != ADMIN_ID:
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)

    # Create the market
    try:
        await data.create_market(
            market_id      = id,
            question       = question,
            details        = details,
            outcomes       = ['YES','NO'],
            subject        = subject,
            creator_id     = str(interaction.user.id),
            b              = b
        )
    except ValueError as e:
        return await interaction.response.send_message(f"❌ {e}", ephemeral=True)

    await interaction.response.send_message(
        f"🔔 Market `{id}` created!\n"
        f"Question: **{question}**\n"
        f"Details: *{details}*\n"
        f"Subject: `{subject}`\n"
        f"b: `{b}`",
        ephemeral=True
    )

    # Public announcement of the new market
    await broadcasts.broadcast_market_created(
        client     = interaction.client,
        market_id  = id,
        question   = question,
        details    = details,
        b          = b
    )


# /markets
@bot.tree.command(
    name="markets",
    description="List all active markets"
)
async def list_markets(interaction: discord.Interaction):
    markets = await data.load_markets()
    lines = []
    for mid,market in markets.items():
        if not market['resolved']:
            odds = market['implied_odds']*100
            lines.append(f"• **{mid}**: {market['question']} | {odds:.1f}%")
    if not lines:
        return await interaction.response.send_message("No active markets.", ephemeral=True)
    await interaction.response.send_message("🏦 Active Markets:\n" + "\n".join(lines), ephemeral=True)


# /delete_market (admin only)
@bot.tree.command(
    name="delete_market",
    description="Admin: delete an existing market (two-step confirmation)"
)
@app_commands.describe(id="The ID of the market to delete")
async def delete_market(interaction: discord.Interaction, id: str):
    # Admin guard
    if interaction.user.id != ADMIN_ID:
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)
    # Check existence
    if id not in await data.load_markets():
        return await interaction.response.send_message(f"❌ Market `{id}` not found.", ephemeral=True)
    # Send the confirmation buttons
    view = DeleteConfirmView(market_id=id)
    await interaction.response.send_message(
        content=(
            f"⚠️ Are you sure you want to delete market `{id}`?\n"
            f"*(Times out in 60 seconds)*"
        ),
        ephemeral=True, view=view
    )


# /details
@bot.tree.command(
    name="details",
    description="Show detailed info about a specific market"
)
@app_commands.describe(
    id="Market ID to show details for"
)
async def details(interaction: discord.Interaction, id: str):
    # Load all markets
    markets = await data.load_markets()
    m = markets.get(id)
    if not m:
        return await interaction.response.send_message(
            f"❌ Market `{id}` not found.",
            ephemeral=True
        )
    # Pull fields from schema
    question    = m["question"]
    b_val       = m["b"]
    implied     = m["implied_odds"] * 100
    yes_shares  = m["shares"]["YES"]
    no_shares   = m["shares"]["NO"]
    volume      = m.get("volume_traded", 0)
    last_trade  = m.get("last_trade") or "N/A"
    # Build the message lines
    lines = [f"**Question:** {question}"]
    # Only show details if non-empty
    details_txt = m.get("details")
    if details_txt:
        lines.append(f"**Details:** *{details_txt}*")
    # Always show b
    lines.append(f"**Liquidity (b-value):** `{b_val}`")
    # Only show subject if non-empty
    subject_txt = m.get("subject")
    if subject_txt:
        lines.append(f"**Subject:** {subject_txt}")
    # Add the dynamic data
    lines.append(f"**Implied odds:** {implied:.2f}%")
    lines.append(f"**Shares:** {yes_shares:.4f} `YES` / {no_shares:.4f} `NO`")
    lines.append(f"**Volume:** ${volume:.2f}")
    lines.append(f"**Last trade:** {last_trade}")
    # Only show resolution_date if non-empty
    resolution_date = m.get("resolution_date")
    if resolution_date:
        lines.append(f"**Resolved:** *{resolution_date}*")
    # Send the assembled message
    await interaction.response.send_message(
        "\n".join(lines),
        ephemeral=True
    )


# /buy
@bot.tree.command(
    name="buy",
    description="Buy Y or N shares by specifying a dollar amount"
)
@app_commands.describe(
    id="Market ID to buy shares in",
    side="Y or N",
    amount="Amount to spend"
)
async def buy(interaction: discord.Interaction, id: str, side: Literal["Y","N"], amount: float):
    user_id = str(interaction.user.id)
    outcome = "YES" if side.upper()=="Y" else "NO"

    # Market & balance checks
    m_dict = await data.load_markets()
    m = m_dict.get(id)
    if not m:
        return await interaction.response.send_message(f"❌ Market `{id}` not found.", ephemeral=True)
    if m['resolved']:
        return await interaction.response.send_message(f"❌ Market `{id}` is already resolved.", ephemeral=True)
    bal = await data.get_balance(user_id)
    if amount<=0 or amount>bal:
        return await interaction.response.send_message(f"❌ Invalid amount. You have ${bal:.2f}.", ephemeral=True)
    
    # LMSR math
    qy,qn,b = m['shares']['YES'], m['shares']['NO'], m['b']
    shares = lmsr.calc_shares(amount,qy,qn,b,outcome)
    price  = amount/shares
    profit_after_fee = (shares - amount)*(1-config.REDEEM_FEE)
    pct    = (profit_after_fee/amount)*100

    # Confirmation view
    view = BuyConfirmView(user_id,id,outcome,amount,shares,price)
    await interaction.response.send_message(
        content=(
            f"🛒 You are buying **{shares:.4f}** `{outcome}` shares for **${amount:.2f}**\n"
            f"Average price: **${price:.4f}**/share\n"
            f"Potential profit (after {config.REDEEM_FEE*100}% fee): **${profit_after_fee:.2f}** ({pct:+.1f}%)\n"
            f"Click `Confirm` or `Cancel`\n"
            f"*(Order expires in 60 seconds)*"
        ),
        ephemeral=True, view=view
    )
    # This is necessary to edit the message later in the view
    view.message = await interaction.original_response()


# /sell command
@bot.tree.command(
    name="sell",
    description="Sell Y or N shares by specifying a percentage of your holdings"
)
@app_commands.describe(
    id="Market ID to sell shares in",
    side="Y or N",
    percent="Percent of your shares to sell (1-100)"
)
async def sell(
    interaction: discord.Interaction,
    id: str,
    side: Literal["Y","N"],
    percent: int
):
    user_id = str(interaction.user.id)
    outcome = "YES" if side.upper()=="Y" else "NO"

    # Market checks
    markets = await data.load_markets()
    m = markets.get(id)
    if not m:
        return await interaction.response.send_message(f"❌ Market `{id}` not found.", ephemeral=True)
    if m['resolved']:
        return await interaction.response.send_message(f"❌ Market `{id}` is already resolved.", ephemeral=True)

    # User position
    bets = await data.load_bets()
    user_bets = bets.get(user_id, {})           # All markets user has bets in
    market_bets = user_bets.get(id, {})         # The dict {'YES': {...}, 'NO': {...}}
    outcome_bet = market_bets.get(outcome, {})  # The dict {'shares': X, …}
    owned = outcome_bet.get('shares', 0)
    if owned <= 0:
        return await interaction.response.send_message(
            f"❌ You have no `{outcome}` shares to sell.",
            ephemeral=True
        )

    # Percent validation
    if percent < 1 or percent > 100:
        return await interaction.response.send_message("❌ Percent must be between 1 and 100.", ephemeral=True)

    shares_to_sell = owned * (percent / 100)

    # Compute proceeds via LMSR cost-difference
    qy, qn, b = m['shares']['YES'], m['shares']['NO'], m['b']
    current_cost = lmsr.lmsr_cost(qy, qn, b)
    if outcome == "YES":
        new_cost = lmsr.lmsr_cost(qy - shares_to_sell, qn, b)
    else:
        new_cost = lmsr.lmsr_cost(qy, qn - shares_to_sell, b)
    amount = current_cost - new_cost
    price  = amount / shares_to_sell if shares_to_sell else 0

    # Confirmation UI
    view = SellConfirmView(user_id, id, outcome, percent, shares_to_sell, price)
    await interaction.response.send_message(
        content=(
            f"💸 You are selling **{shares_to_sell:.4f}** `{outcome}` shares "
            f"({percent}% of your position)\n"
            f"Average price: **${price:.4f}**/share\n"
            f"You will receive: **${amount:.2f}**\n"
            f"Click `Confirm` or `Cancel`\n"
            f"*(Order expires in 60 seconds)*"
        ),
        ephemeral=True,
        view=view
    )
    view.message = await interaction.original_response()


# /bal
@bot.tree.command(name="bal", description="Check your cash balance")
async def bal(interaction: discord.Interaction):
    bal = await data.get_balance(str(interaction.user.id))
    await interaction.response.send_message(
        content=f"💰 Your cash balance is **${bal:.2f}**", ephemeral=True
    )


# /port
@bot.tree.command(
    name="port",
    description="View your portfolio including cash and all open bets"
)
async def port(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    bal = await data.get_balance(user_id)
    bets_dict = await data.load_bets()
    bets = bets_dict.get(user_id, {})
    markets = await data.load_markets()

    # Compute total bet value and build lines, skip missing or resolved markets
    total_bet_val=0
    lines = [
    "Market         | Side |   Shares    |    Value    |   Unrealiz. Profit",
    "---------------|------|-------------|-------------|--------------------"
    ]
    for mid,pos in bets.items():
        m=markets.get(mid)
        if not m or m['resolved']: continue
        # Current marginal price for YES
        p_yes=lmsr.lmsr_price(m['shares']['YES'],m['shares']['NO'],m['b'])
        # For each position owned:
        for outcome, market in pos.items():
            shares = market.get('shares', 0)
            if shares <= 0:
                continue    
            # Calculate current values of each position and append to open bets
            price = p_yes if outcome == "YES" else (1 - p_yes)
            value = shares * price
            cost_basis = market.get('cost_basis', 0)
            profit = value - cost_basis
            total_bet_val += value
            side_label = "YES" if outcome == "YES" else "NO"
            lines.append(
            f"{mid:<14} | {side_label:<4} | {shares:11.4f} | ${value:10.2f} | ${profit:17.2f}"
            )

    # Totals
    total = bal + total_bet_val
    # Header
    header = (
        f"💰 Cash: **${bal:.2f}**\n"
        f"📈 Open Bets: **${total_bet_val:.2f}**\n"
        f"🔖 Total Portfolio: **${total:.2f}**"
    )
    # Build response
    if not lines:
        body = "You have no open bets."
    else:
        table = "```\n" + "\n".join(lines) + "\n```"

    await interaction.response.send_message(
        content=f"{header}\n\nOpen Bets:\n{table}",
        ephemeral=True
    )


# /deposit (admin only)
@bot.tree.command(
    name="deposit",
    description="Admin: deposit cash into a user’s account"
)
@app_commands.describe(
    user="The user to credit",
    amount="Dollar amount to deposit"
)
async def deposit(
    interaction: discord.Interaction,
    user: discord.User,
    amount: float
):
    # Admin guard
    if interaction.user.id != ADMIN_ID:
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)
    # Update balances
    target_id = str(user.id)
    await data.update_balance(target_id, amount)
    new_bal = await data.get_balance(target_id)
    # Log in transfers.db
    await data.log_transfer(
        type="deposit",
        from_user=None,
        to_user=target_id,
        amount=amount,
        balance=new_bal
    )
    # Send confirmation
    await interaction.response.send_message(
        f"✅ Deposited **${amount:.2f}** to {user.mention}. New balance: **${new_bal:.2f}**",
        ephemeral=True
    )


# /withdraw (admin only)
@bot.tree.command(
    name="withdraw",
    description="Admin: withdraw cash from a user’s account"
)
@app_commands.describe(
    user="The user to debit",
    amount="Dollar amount to withdraw"
)
async def withdraw(
    interaction: discord.Interaction,
    user: discord.User,
    amount: float
):
    # Admin guard; balance check
    if interaction.user.id != ADMIN_ID:
        return await interaction.response.send_message("❌ You don’t have permission.", ephemeral=True)
    target_id = str(user.id)
    current = await data.get_balance(target_id)
    if amount > current:
        return await interaction.response.send_message(
            f"❌ Cannot withdraw ${amount:.2f}; user only has ${current:.2f}.",
            ephemeral=True
        )
    # Update balance
    await data.update_balance(target_id, -amount)
    new_bal = await data.get_balance(target_id)
    # Log in transfers.db
    await data.log_transfer(
        type="withdrawal",
        from_user=target_id,
        to_user=None,
        amount=amount,
        balance=new_bal
    )
    # Send confirmation
    await interaction.response.send_message(
        f"✅ Withdrew **${amount:.2f}** from {user.mention}. New balance: **${new_bal:.2f}**",
        ephemeral=True
    )


# /send
@bot.tree.command(
    name="send",
    description="Send cash to another user."
)
@app_commands.describe(
    user="User you want to send money to",
    amount="Amount to send (input number without $ symbol)"
)
async def send(
    interaction: discord.Interaction,
    user: discord.User,
    amount: float
):
    sender_id = str(interaction.user.id)
    recipient_id = str(user.id)

    # Prevent sending to yourself
    if recipient_id == sender_id:
        return await interaction.response.send_message(
            "❌ You cannot send money to yourself.",
            ephemeral=True
        )

    # Amount validation
    if amount <= 0:
        return await interaction.response.send_message(
            "❌ Please specify a positive number.",
            ephemeral=True
        )

    # Check sender's balance
    sender_bal = await data.get_balance(sender_id)
    if amount > sender_bal:
        return await interaction.response.send_message(
            f"❌ Insufficient funds: you only have ${sender_bal:.2f}.",
            ephemeral=True
        )

    # Build confirmation view
    view = SendConfirmView(
        sender_id=sender_id,
        recipient_id=recipient_id,
        amount=amount
    )

    # Send ephemeral confirmation prompt
    await interaction.response.send_message(
        content=(
            f"⚠️ You are about to send **${amount:.2f}** to {user.mention}.\n"
            f"Your current balance is **${sender_bal:.2f}**.\n"
            f"Click `Confirm` or `Cancel`\n"
            f"*(Times out in 60 seconds)*"
        ),
        ephemeral=True,
        view=view
    )


# /resolve
@bot.tree.command(
    name="resolve",
    description="Admin: resolve a market and payout winners"
)
@app_commands.describe(
    id="Market ID to resolve",
    outcome="Winning side: Y or N"
)
async def resolve_market(
    interaction: discord.Interaction,
    id: str,
    outcome: Literal["Y","N"]
):
    # Admin guard
    if interaction.user.id != ADMIN_ID:
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)

    correct = "YES" if outcome.upper() == "Y" else "NO"
    try:
        question, implied, total_paid, total_lost = await data.resolve_market(id, correct)
    except ValueError as e:
        return await interaction.response.send_message(f"❌ {e}", ephemeral=True)

    # Public broadcast
    await broadcasts.broadcast_resolution(
        client           = interaction.client,
        market_id        = id,
        market_name      = question,
        correct_side     = correct,
        implied_odds     = implied,
        total_paid       = total_paid,
        total_lost_shares= total_lost
    )

    # Send confirmation to admin
    await interaction.response.send_message(
        f"🔔 Market `{id}` resolved as `{correct}`.\n"
        f"Paid out **${total_paid:.2f}**. Losers forfeited **{total_lost:.2f}** shares.",
        ephemeral=True
    )


# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)