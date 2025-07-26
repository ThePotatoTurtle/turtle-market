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
        f"**{shares:.4f}** `{outcome}` shrs {verb} for **${amount:.2f}**\n"
        f"Current implied odds: **{implied_odds*100:.2f}%** {odds_change}"
    )

    # Send it publicly
    await chan.send(text)


# Broadcast market creations to MARKETS_CHANNEL_ID
async def broadcast_market_created(
    client: discord.Client,
    market_id: str,
    question: str,
    details: str | None,
    b: float
):
    """
    Publicly announces a newly created market.
    """
    # Get the configured channel
    chan = client.get_channel(config.MARKETS_CHANNEL_ID)
    if chan is None:
        chan = await client.fetch_channel(config.MARKETS_CHANNEL_ID)

    # Build & send the message
    await chan.send(
        f"📢 **New market:** `{market_id}`\n"
        f"• **Topic**: {question}\n"
        f"• **Details:** *{details or '—'}*\n"
        f"• **Liquidity (b-value):** `{b}`"
    )


# Broadcast market resolutions to MARKETS_CHANNEL_ID
async def broadcast_resolution(
    client: discord.Client,
    market_id: str,
    market_name: str,
    correct_side: str,
    implied_odds: float,
    total_paid: float,
    total_lost_shares: float
):
    """
    Publicly announce that a market has been resolved.
    """
    chan = client.get_channel(config.MARKETS_CHANNEL_ID)
    if chan is None:
        chan = await client.fetch_channel(config.MARKETS_CHANNEL_ID)

    await chan.send(
        f"📢 **Market resolved:** `{market_id}`\n"
        f"• **Topic:** {market_name}\n"
        f"• **Outcome:** `{correct_side}`\n"
        f"• **Implied odds at resolution:** {implied_odds*100:.2f}%\n"
        f"• **Total payout:** ${total_paid:.2f}\n"
        f"• **Total forfeited shares:** {total_lost_shares:.2f}"
    )