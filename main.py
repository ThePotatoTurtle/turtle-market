import os
import discord
from discord import app_commands
from dotenv import load_dotenv
import storage

# 1) Load .env
load_dotenv()
DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID", 0))
ADMIN_ID    = int(os.getenv("ADMIN_ID",    0))
TOKEN       = os.getenv("DISCORD_TOKEN")

# 2) Bot subclass
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

# 3) Instantiate the bot
bot = PredictionBot()

# 4) Events
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

# 5) Slash commands (now that `bot` exists)

@bot.tree.command(
    name="create_market",
    description="Admin: create a YES/NO market with a custom public ID"
)
@app_commands.describe(
    id="Unique ID for this market (e.g. EVENT2025)",
    question="The question for this market"
)
async def create_market(interaction: discord.Interaction, id: str, question: str):
    # Admin check
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return

    try:
        storage.create_market(market_id=id, question=question, creator_id=interaction.user.id)
    except ValueError as e:
        await interaction.response.send_message(f"❌ {e}", ephemeral=True)
        return

    await interaction.response.send_message(f"🔔 Market `{id}` created!", ephemeral=True)

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

# 6) Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)

