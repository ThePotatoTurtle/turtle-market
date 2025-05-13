@bot.tree.command(
    name="create_market",
    description="Admin: create a YES/NO market with a custom public ID"
)
@app_commands.describe(
    id="Unique ID for this market (e.g. EVENT2025)",
    question="The question for this market"
)
async def create_market(
    interaction: discord.Interaction,
    id: str,
    question: str
):
    try:
        storage.create_market(
            market_id=id,
            question=question,
            creator_id=interaction.user.id
        )
    except ValueError as e:
        await interaction.response.send_message(
            f"❌ {e}",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"🔔 Market created!\nID: `{id}`\nQuestion: **{question}**",
        ephemeral=True
    )
