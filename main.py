import os
from typing import Optional, Literal
import discord
from discord import app_commands
from discord.ui import View, button
from discord import ButtonStyle
from dotenv import load_dotenv
import storage, lmsr, config, transactions, broadcasts


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
    # Init all logs
    await transactions.init_trades_db()
    await transactions.init_resolved_db()
    await transactions.init_transfers_db()

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
            return await interaction.response.send_message(
                "❌ No permission.", ephemeral=True
            )

        try:
            storage.delete_market(self.market_id)
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
            content="❌ Deletion canceled.",
            view=None
        )


# Confirmation view for /buy
class BuyConfirmView(View):
    def __init__(self, user_id, market_id, outcome, amount, shares, price):
        super().__init__(timeout=60)
        self.user_id   = user_id
        self.market_id = market_id
        self.outcome   = outcome
        self.amount    = amount
        self.shares    = shares
        self.price     = price

    @button(label="Confirm", style=ButtonStyle.primary)
    async def confirm(self, interaction, button):
        if str(interaction.user.id) != self.user_id:
            return await interaction.response.send_message("❌ Not your order.", ephemeral=True)

        # Update user_balances.json and user_bets.json
        storage.update_balance(self.user_id, -self.amount)
        storage.update_balance(config.POOL_ID, self.amount)
        storage.add_bet(self.user_id, self.market_id, self.outcome, self.shares)

        # Derive implied odds for YES
        implied_odds = self.price if self.outcome=="YES" else 1-self.price

        # Update markets.json with share counts
        markets = storage.load_markets()
        m = markets[self.market_id]
        m['shares'][self.outcome] += self.shares
        
        # Compute instantaneous LMSR price for YES
        qy = m['shares']['YES']
        qn = m['shares']['NO']
        b  = m['b']
        implied_odds = lmsr.lmsr_price(qy, qn, b)  # Always marginal price

        # Update markets.json with implied odds
        m["implied_odds"] = implied_odds
        storage.save_markets(markets)

        # Log into trades.db
        await transactions.log_trade(
            user_id   = self.user_id,
            market_id = self.market_id,
            outcome   = self.outcome,
            shares    = self.shares,   # positive for buy
            amount    = self.amount,   # positive dollars spent
            price     = self.price
        )

        # Compute profit
        profit_after_fee = (self.shares - self.amount)*(1-config.REDEEM_FEE)
        pct    = (profit_after_fee / self.amount)*100 if self.amount else 0

        # Broadcast the buy
        await broadcasts.broadcast_trade(
            client         = interaction.client,
            market_id      = self.market_id,
            market_name    = m["question"],
            side           = "BUY",
            outcome        = self.outcome,
            shares         = self.shares,
            amount         = self.amount,
            implied_odds   = implied_odds
        )

        await interaction.response.edit_message(
            content=(
                f"✅ Bought **{self.shares:.4f}** `{self.outcome}` shares in `{self.market_id}`\n"
                f"Average price: **${self.price:.4f}**/share\n"
                f"Spent: **${self.amount:.2f}**\n"
                f"Potential profit (after {config.REDEEM_FEE*100}% fee): **${profit_after_fee:.2f}** ({pct:.1f}%)\n"
                f"New balance: **${storage.get_balance(self.user_id):.2f}**"
            ),
            view=None
        )

    @button(label="Cancel", style=ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(
            content="❌ Buy order canceled.", view=None
        )



# Slash commands

# /create_market (admin only)
@bot.tree.command(
    name="create_market",
    description="Admin: create a YES/NO market with ID, subject, b-parameter, and resolution date"
)
@app_commands.describe(
    id="Unique ID for this market (e.g. EVENT2025)",
    question="The question for this market",
    subject="Optional subject ID (to block self-bets)",
    b=f"LMSR b-parameter (liquidity), default={config.DEFAULT_B}",
    resolution_date="Date for resolution (YYYY-MM-DD)"
)
async def create_market(
    interaction: discord.Interaction,
    id: str,
    question: str,
    subject: Optional[str] = None,
    b: float = config.DEFAULT_B,
    resolution_date: Optional[str] = None
):
    # Admin guard
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return

    # Create the market
    try:
        storage.create_market(
            market_id=id,
            question=question,
            subject=subject,
            creator_id=interaction.user.id,
            b=b,
            resolution_date=resolution_date
        )
    except ValueError as e:
        await interaction.response.send_message(f"❌ {e}", ephemeral=True)
        return

    await interaction.response.send_message(
        f"🔔 Market `{id}` created!\n"
        f"Question: **{question}**\n"
        f"Subject: `{subject}`\n"
        f"b: `{b}`\n"
        f"Resolution date: `{resolution_date}`",
        ephemeral=True
    )

# /markets
@bot.tree.command(
    name="markets",
    description="List all active markets"
)
async def list_markets(interaction: discord.Interaction):
    markets = storage.load_markets()
    if not markets:
        await interaction.response.send_message("No active markets.", ephemeral=True)
        return

    lines = [f"• **{mid}**: {data['question']}" for mid, data in markets.items()]
    msg = "**Active Markets:**\n" + "\n".join(lines)
    await interaction.response.send_message(msg, ephemeral=True)

# /delete_market (admin only)
@bot.tree.command(
    name="delete_market",
    description="Admin: delete an existing market (two-step confirmation)"
)
@app_commands.describe(
    id="The ID of the market to delete"
)
async def delete_market(interaction: discord.Interaction, id: str):
    # Admin guard
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return

    # Check existence
    if id not in storage.load_markets():
        await interaction.response.send_message(
            f"❌ Market `{id}` not found.",
            ephemeral=True
        )
        return

    # Send the confirmation buttons
    view = DeleteConfirmView(market_id=id)
    await interaction.response.send_message(
        content=(
            f"⚠️ Are you sure you want to delete market `{id}`?\n"
            f"*(Times out in 60 seconds)*"
        ),
        ephemeral=True,
        view=view
    )

# /buy
@bot.tree.command(
    name="buy",
    description="Buy Y or N shares by specifying a dollar amount"
)
@app_commands.describe(
    id="Market ID to trade on",
    side="Y or N",
    amount="Dollar amount you wish to spend (input number without $ symbol)"
)
async def buy(interaction, id: str, side: Literal["Y","N"], amount: float):
    user_id = str(interaction.user.id)
    side = side.upper()
    outcome = "YES" if side == "Y" else "NO"

    # --- Market & balance checks (same as before) ---
    markets = storage.load_markets()
    if id not in markets:
        return await interaction.response.send_message(f"❌ Market `{id}` not found.", ephemeral=True)
    m = markets[id]
    if m.get("resolved"):
        return await interaction.response.send_message(f"❌ Market `{id}` is resolved.", ephemeral=True)

    bal = storage.get_balance(user_id)
    if amount <= 0 or amount > bal:
        return await interaction.response.send_message(f"❌ Invalid amount. You have ${bal:.2f}.", ephemeral=True)

    # --- LMSR math ---
    qy, qn, b = m['shares']['YES'], m['shares']['NO'], m['b']
    shares = lmsr.calc_shares(amount, qy, qn, b, outcome)
    price  = (amount / shares)
    
    profit_after_fee = (shares - amount)*(1-config.REDEEM_FEE)
    pct = (profit_after_fee / amount) * 100 if amount else 0

    view = BuyConfirmView(user_id, id, outcome, amount, shares, price)
    await interaction.response.send_message(
        content=(
            f"💹 With **${amount:.2f}**, you can buy **{shares:.4f}** `{outcome}` shares\n"
            f"Average price: **${price:.4f}**/share\n"
            f"Potential profit (after {config.REDEEM_FEE*100}% fee): **${profit_after_fee:.2f}** ({pct:.1f}%)\n"
            f"Click `Confirm` or `Cancel`\n"
            f"*(Times out in 60 seconds)*\n\n"
        ),
        ephemeral=True,
        view=view
    )

# /cash
@bot.tree.command(
    name="cash",
    description="Check your current cash balance"
)
async def cash(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    balance = storage.get_balance(user_id)
    await interaction.response.send_message(
        content=f"💰 Your cash balance is **${balance:.2f}**",
        ephemeral=True
    )

# /port
@bot.tree.command(
    name="port",
    description="View your portfolio including cash and all open bets"
)
async def port(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    # Cash balance
    balance = storage.get_balance(user_id)

    # Load user bets and markets
    all_bets = storage.load_bets().get(user_id, {})
    markets  = storage.load_markets()

    # Compute total bet value and build lines
    total_bets_value = 0.0
    lines = []
    for mid, pos in all_bets.items():
        market = markets.get(mid)
        # Skip missing or resolved markets
        if not market or market.get("resolved"):
            continue

        # Current marginal price for YES
        qy = market["shares"]["YES"]
        qn = market["shares"]["NO"]
        b  = market["b"]
        p_yes = lmsr.lmsr_price(qy, qn, b)

        # For each side owned
        for outcome, shares in pos.items():
            if shares <= 0:
                continue
            # Choose price per share
            price = p_yes if outcome == "YES" else (1 - p_yes)
            value = shares * price
            total_bets_value += value
            side_label = "YES" if outcome == "YES" else "NO"
            lines.append(
                f"• **{mid}** | {side_label} | {shares:.4f} shrs | ${value:.2f}"
            )

    # Totals
    total_portfolio = balance + total_bets_value
    header = (
        f"💰 Cash: **${balance:.2f}**\n"
        f"📈 Open Bets: **${total_bets_value:.2f}**\n"
        f"🔖 Total Portfolio: **${total_portfolio:.2f}**"
    )

    # Build response
    if not lines:
        body = "You have no open bets."
    else:
        body = "**Open Bets:**\n" + "\n".join(lines)

    await interaction.response.send_message(
        content=f"{header}\n\n{body}",
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
        return await interaction.response.send_message("❌ You don’t have permission.", ephemeral=True)
    target_id = str(user.id)
    # Update JSON balance
    storage.update_balance(target_id, amount)
    new_bal = storage.get_balance(target_id)
    # Log in transfers.db
    await transactions.log_transfer(
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
    current = storage.get_balance(target_id)
    if amount > current:
        return await interaction.response.send_message(
            f"❌ Cannot withdraw ${amount:.2f}; user only has ${current:.2f}.",
            ephemeral=True
        )
    # Update JSON balance
    storage.update_balance(target_id, -amount)
    new_bal = storage.get_balance(target_id)
    # Log in transfers.db
    await transactions.log_transfer(
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


# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)