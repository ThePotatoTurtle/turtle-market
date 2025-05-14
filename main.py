import os
from typing import Optional
import discord
from discord import app_commands
from dotenv import load_dotenv
import storage


# Load .env
load_dotenv()
DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID", 0))
ADMIN_ID    = int(os.getenv("ADMIN_ID", 0))
TOKEN       = os.getenv("DISCORD_TOKEN")


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
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")


# Slash commands

# /create_market
@bot.tree.command(
    name="create_market",
    description="Admin: create a YES/NO market with ID, subject, b-parameter, and resolution date"
)
@app_commands.describe(
    id="Unique ID for this market (e.g. EVENT2025)",
    question="The question for this market",
    subject="Optional subject ID (to block self-bets)",
    b=f"LMSR b-parameter (liquidity), default={storage.DEFAULT_B}",
    resolution_date="Date for resolution (YYYY-MM-DD)"
)
async def create_market(
    interaction: discord.Interaction,
    id: str,
    question: str,
    subject: Optional[str] = None,
    b: float = storage.DEFAULT_B,
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
    msg = "__**Active Markets:**__\n" + "\n".join(lines)
    await interaction.response.send_message(msg, ephemeral=True)


# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)

