# graphs.py
# Odds-over-time graph generation for markets.
# History is reconstructed by replaying the trades log through the LMSR price
# function (validated to reproduce stored market state exactly), so no odds
# snapshots need to be stored.

import os
import math
import datetime

import matplotlib
matplotlib.use("Agg")  # Headless backend; must be set before importing pyplot
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.interpolate import PchipInterpolator

import lmsr

# Folder where all generated graphs are saved for future reference
BASE = os.path.dirname(__file__)
GRAPHS_DIR = os.path.join(BASE, 'graphs')

# Odds a resolution outcome settles at
RESOLUTION_ODDS = {'YES': 1.0, 'NO': 0.0, 'HALF': 0.5}
RESOLUTION_COLORS = {'YES': '#2ecc71', 'NO': '#e74c3c', 'HALF': '#7f8c8d'}
# Marker glyphs (font-safe: real emoji don't render in matplotlib's default font)
RESOLUTION_SYMBOLS = {'YES': '✓', 'NO': '✗', 'HALF': '½'}

UTC = datetime.timezone.utc


def parse_ts(ts: str) -> datetime.datetime:
    """Parse an ISO-8601 timestamp from the DB into an aware UTC datetime."""
    dt = datetime.datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def odds_history(market: dict, trades: list, now: datetime.datetime | None = None):
    """
    Build the implied-odds timeline for a market by replaying its trades.

    market: dict from data.load_markets() (needs b, created_at, resolved,
            resolution, resolution_date).
    trades: list of (outcome, shares, timestamp) from data.load_market_trades(),
            shares signed (buys positive, sells negative), in execution order.

    Returns (points, resolution_point):
      points: list of (datetime, odds) — starts at 50% on creation, one point
              after each trade, and ends flat at "now" (active markets) or the
              resolution date (resolved markets). Odds truly are constant
              between trades, so the flat tail is honest, not extrapolation.
      resolution_point: (datetime, odds) for the settled outcome (100%/0%/50%),
              or None for active markets.
    """
    b = market['b']
    created = parse_ts(market['created_at'])

    q_yes = q_no = 0.0
    trade_points: list[tuple[datetime.datetime, float]] = []
    for outcome, shares, ts in trades:
        if outcome == 'YES':
            q_yes += shares
        else:
            q_no += shares
        trade_points.append((parse_ts(ts), lmsr.lmsr_price(q_yes, q_no, b)))

    # Terminal time: odds hold their last value until now / resolution
    resolution_point = None
    if market['resolved']:
        end = parse_ts(market['resolution_date'])
        resolution_point = (end, RESOLUTION_ODDS[market['resolution']])
    else:
        end = now or datetime.datetime.now(UTC)

    # Start at creation, clamped for legacy markets whose backfilled
    # created_at postdates their first trade or resolution date.
    start = min([created, end] + ([trade_points[0][0]] if trade_points else []))
    if start >= end:
        # Degenerate zero-duration timeline (e.g. zero-trade legacy market
        # backfilled to its resolution date) — show a 1-day window.
        start = end - datetime.timedelta(days=1)
    points = [(start, 0.5)] + trade_points
    points.append((end, points[-1][1]))

    # Enforce strictly increasing timestamps (PCHIP requirement): for
    # duplicate times keep the last odds; drop any out-of-order stragglers.
    cleaned: list[tuple[datetime.datetime, float]] = []
    for t, p in points:
        if cleaned and t == cleaned[-1][0]:
            cleaned[-1] = (t, p)
        elif cleaned and t < cleaned[-1][0]:
            continue
        else:
            cleaned.append((t, p))
    return cleaned, resolution_point


def y_bounds(odds: list[float]) -> tuple[float, float]:
    """
    Auto-scale the y-axis (in percent) to the nearest 5% increment strictly
    below/above the lowest/highest odds, clamped to [0, 100].
    """
    lo = min(odds) * 100
    hi = max(odds) * 100
    ymin = 5 * math.floor(lo / 5)
    if ymin == lo:
        ymin -= 5
    ymax = 5 * math.ceil(hi / 5)
    if ymax == hi:
        ymax += 5
    return max(0.0, ymin), min(100.0, ymax)


def render_market_graph(market_id: str, market: dict, trades: list,
                        out_dir: str = GRAPHS_DIR) -> str:
    """
    Render a market's odds-over-time graph to a PNG and return its path.
    Saved as {out_dir}/{market_id}_{YYYYMMDD-HHMMSS}.png.
    """
    now = datetime.datetime.now(UTC)
    points, resolution_point = odds_history(market, trades, now=now)

    times = [t for t, _ in points]
    odds = [p for _, p in points]
    all_odds = odds + ([resolution_point[1]] if resolution_point else [])
    ymin, ymax = y_bounds(all_odds)

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=144)

    # Smoothed line: PCHIP (monotone cubic) interpolation through the actual
    # trade points — smooth, but never overshoots to odds that never traded.
    x = [t.timestamp() for t in times]
    y = [p * 100 for p in odds]
    if len(x) > 2:
        interp = PchipInterpolator(x, y)
        n_dense = 400
        xs = [x[0] + (x[-1] - x[0]) * i / (n_dense - 1) for i in range(n_dense)]
        ys = interp(xs)
        dense_times = [datetime.datetime.fromtimestamp(t, tz=UTC) for t in xs]
        ax.plot(dense_times, ys, color='#3498db', linewidth=2, zorder=2)
    else:
        ax.plot(times, y, color='#3498db', linewidth=2, zorder=2)

    # Mark the actual odds snapshots (trade points)
    ax.plot(times, y, 'o', color='#2c3e50', markersize=3.5, alpha=0.7, zorder=3)

    # Resolved markets: connect the line to the settled odds and mark them
    if resolution_point:
        res_time, res_odds = resolution_point
        outcome = market['resolution']
        color = RESOLUTION_COLORS[outcome]
        # Vertical connector from the last traded odds up/down to the settlement
        ax.plot([times[-1], res_time], [y[-1], res_odds * 100],
                color='#3498db', linewidth=2, zorder=2)
        # Outcome symbol at the settlement point: ✓ YES / ✗ NO / ½ HALF
        ax.text(res_time, res_odds * 100, RESOLUTION_SYMBOLS[outcome],
                fontsize=16, fontweight='bold', color=color,
                ha='center', va='center', zorder=5)
        # Label placed left of the point, nudged off the axis edge at 0%/100%
        if res_odds >= 0.75:
            dy, va = -6, 'top'
        elif res_odds <= 0.25:
            dy, va = 6, 'bottom'
        else:
            dy, va = 8, 'bottom'
        ax.annotate(f"Resolved {outcome} ({res_odds * 100:.0f}%)",
                    xy=(res_time, res_odds * 100), xytext=(-14, dy),
                    textcoords='offset points', ha='right', va=va,
                    color=color, fontsize=9, fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.25', fc='white',
                              ec='none', alpha=0.8))

    # Axes: real-time x scale, auto-fitted y in 5% steps.
    # Small x-margin keeps end-point markers off the plot edge.
    ax.margins(x=0.02)
    ax.set_ylim(ymin, ymax)
    locator = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    ax.set_ylabel('Implied YES odds (%)')
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    question = market['question']
    if len(question) > 80:
        question = question[:77] + '...'
    ax.set_title(question, fontsize=11, fontweight='bold')
    fig.text(0.99, 0.01, f"{market_id} • generated {now:%Y-%m-%d %H:%M} UTC",
             ha='right', va='bottom', fontsize=7, color='#7f8c8d')
    fig.tight_layout()

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{market_id}_{now:%Y%m%d-%H%M%S}.png")
    fig.savefig(path)
    plt.close(fig)
    return path
