import discord
import config

# Broadcast buys and sells to BROADCAST_CHANNEL_ID
async def broadcast_trade(
    client: discord.Client,
    market_id: str,
    market_name: str,
    side: str,        # “BUY” or “SELL”
    outcome: str,     # “YES” or “NO”
    shares: float,
    amount: float,
    implied_odds: float
):
    """
    Send a permanent public message to the BROADCAST_CHANNEL_ID summarizing the trade.
    """
    # Fetch or cache the channel
    chan = client.get_channel(config.BROADCAST_CHANNEL_ID)
    if chan is None:
        chan = await client.fetch_channel(config.BROADCAST_CHANNEL_ID)

    # Format the message
    verb = "BOUGHT" if side == "BUY" else "SOLD"
    emoji = "📈" if side == "BUY" else "📉"
    odds_change = "⬇️" if (side == "BUY" and outcome == "NO") or (side == "SELL" and outcome == "YES") else "⬆️"
    text = (
        f"{emoji} `{market_id}`: {market_name}\n"
        f"New trade: **{shares:.4f}** `{outcome}` shares {verb} for **${amount:.2f}**\n"
        f"Current implied odds: **{implied_odds*100:.2f}%** {odds_change}"
    )

    # Send it publicly
    await chan.send(text)


