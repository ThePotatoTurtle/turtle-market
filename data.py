# data.py
# Unified storage module loading schema from schema.sql and performing ACID-compliant transaction operations

import os, aiosqlite, asyncio, datetime
from typing import Dict, Any, Optional
import config

# Path to the single unified database file
BASE = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE, 'data.db')

# Path to schema file
SCHEMA_PATH = os.path.join(BASE, 'schema.sql')

# Initialization
async def init_db():
    """
    Initialize the unified database by executing schema.sql.
    All tables (market_info, market_data, resolutions, trades,
    transfers, user_balances, user_bets) created atomically.
    """
    # Read schema SQL
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema_sql = f.read()

    # Execute entire schema in one transaction
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(schema_sql)
        await db.commit()


# Market operations 

async def create_market(
    market_id: str,
    question: str,
    outcomes=('YES', 'NO'),
    details: Optional[str] = None,
    subject: Optional[str] = None,
    creator_id: Optional[str] = None,
    b: float = config.DEFAULT_B
) -> None:
    """
    Create a new market atomically: insert into market_info and market_data.
    Raise ValueError if market_id already exists.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        # Use a transaction to ensure both inserts or none
        async with db.execute("SELECT 1 FROM market_info WHERE market_id = ?", (market_id,)) as cur:
            if await cur.fetchone():
                raise ValueError(f"Market ID '{market_id}' already exists")
        # Begin transaction
        await db.execute(
            "INSERT INTO market_info(market_id, question, details, b, subject, creator_id)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (market_id, question, details, b, subject, creator_id)
        )
        await db.execute(
            "INSERT INTO market_data(market_id) VALUES (?)",
            (market_id,)
        )
        await db.commit()

async def load_markets() -> Dict[str, Dict[str, Any]]:
    """
    Load all markets by joining market_info and market_data.
    Return a dict: market_id -> fields.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT i.market_id, i.question, i.details, i.b, i.subject, i.creator_id,"
            " d.yes_shares, d.no_shares, d.resolved, d.resolution, d.resolution_date,"
            " d.implied_odds, d.last_trade, d.volume_traded"
            " FROM market_info i"
            " JOIN market_data d ON i.market_id = d.market_id"
        )
        rows = await cursor.fetchall()
        markets: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            markets[row['market_id']] = {
                'question':        row['question'],
                'details':         row['details'],
                'b':               row['b'],
                'subject':         row['subject'],
                'creator':         row['creator_id'],
                'shares': {
                    'YES': row['yes_shares'],
                    'NO':  row['no_shares']
                },
                'resolved':        bool(row['resolved']),
                'resolution':      row['resolution'],
                'resolution_date': row['resolution_date'],
                'implied_odds':    row['implied_odds'],
                'last_trade':      row['last_trade'],
                'volume_traded':   row['volume_traded']
            }
        return markets

async def save_markets(markets: Dict[str, Dict[str, Any]]) -> None:
    """
    Atomically update static info and live data for all markets.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        # Wrap all updates in a single transaction
        for mid, data in markets.items():
            await db.execute(
                "UPDATE market_info SET question=?, details=?, b=?, subject=?, creator_id=?"
                " WHERE market_id=?",
                (
                    data['question'], data['details'], data['b'], data['subject'], data['creator'],
                    mid
                )
            )
            await db.execute(
                "UPDATE market_data SET yes_shares=?, no_shares=?, resolved=?, resolution=?, resolution_date=?, implied_odds=?, last_trade=?, volume_traded=?"
                " WHERE market_id=?",
                (
                    data['shares']['YES'], data['shares']['NO'], int(data['resolved']),
                    data['resolution'], data['resolution_date'], data['implied_odds'],
                    data['last_trade'], data['volume_traded'], mid
                )
            )
        await db.commit()

async def delete_market(market_id: str) -> None:
    """
    Atomically delete a market's live data and static info.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM market_data WHERE market_id=?", (market_id,))
        await db.execute("DELETE FROM market_info WHERE market_id=?", (market_id,))
        await db.commit()


# Balance operations

async def get_balance(user_id: str) -> float:
    """
    Retrieve or initialize a user's balance.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT balance FROM user_balances WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return row[0]
        bal = config.DEFAULT_USER_BALANCE
        await db.execute(
            "INSERT INTO user_balances(user_id, balance, volume_traded, volume_resolved) "
            "VALUES (?, ?, 0, 0)",
            (user_id, bal)
        )
        await db.commit()
        return bal

async def update_balance(user_id: str, delta: float) -> None:
    """
    Atomically update a user's balance by delta.
    """
    bal = await get_balance(user_id)
    new_bal = bal + delta
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE user_balances SET balance = ? WHERE user_id = ?",
            (new_bal, user_id)
        )
        await db.commit()


# Bets operations

async def load_bets() -> Dict[str, Dict[str, dict]]:
    """
    Load all user bets. Return nested dict: user_id -> (market_id -> {shares, cost_basis, last_trade}).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, market_id, outcome, shares, cost_basis, last_trade FROM user_bets"
        )
        rows = await cursor.fetchall()
        bets: Dict[str, Dict[str, dict]] = {}
        for user_id, mid, outcome, shares, cost_basis, last_trade in rows:
            user = bets.setdefault(user_id, {})
            pos  = user.setdefault(mid, {'YES': {}, 'NO': {}})
            pos[outcome] = {
                'shares': shares,
                'cost_basis': cost_basis,
                'last_trade': last_trade
            }
        return bets

async def add_bet(user_id: str, market_id: str, outcome: str, delta_shares: float, delta_cost: float) -> None:
    """
    Atomically add or remove shares in a user's position for a market.
    Record cost basis and last trade timestamp.
    """
    bets = await load_bets()
    current_bet = bets.get(user_id, {}).get(market_id, {}).get(outcome,
                        {'shares': 0.0, 'cost_basis': 0.0})
    current_shares = current_bet.get('shares', 0.0)
    current_cost   = current_bet.get('cost_basis', 0.0)
    new_shares = current_shares + delta_shares
    new_cost   = current_cost + delta_cost
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        if new_shares <= 0:
            await db.execute(
                "DELETE FROM user_bets WHERE user_id=? AND market_id=? AND outcome=?",
                (user_id, market_id, outcome)
            )
        else:
            await db.execute(
                "INSERT OR REPLACE INTO user_bets(user_id, market_id, outcome, shares, cost_basis, last_trade) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, market_id, outcome, new_shares, new_cost, now)
            )
        await db.commit()


# Transaction operations

async def log_trade(user_id: str, market_id: str, outcome: str, shares: float, amount: float, price: float, balance: float) -> None:
    """
    Log a buy/sell transaction atomically.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Log the trade in user_trades
        await db.execute(
            "INSERT INTO trades(user_id, market_id, outcome, shares, amount, price, balance, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ",
            (user_id, market_id, outcome, shares, amount, price, balance,
             datetime.datetime.now(datetime.timezone.utc).isoformat())
        )
        # Increment the user’s volume_traded by the absolute $ amount
        await db.execute(
            "UPDATE user_balances "
            "SET volume_traded = volume_traded + abs(?) "
            "WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

async def log_resolve(user_id: str, market_id: str, outcome: str, shares: float, redeemed: float) -> None:
    """
    Log a resolution event atomically.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO resolutions(user_id, market_id, outcome, shares, redeemed, timestamp) VALUES (?, ?, ?, ?, ?, ?) ",
            (user_id, market_id, outcome, shares, redeemed,
             datetime.datetime.now(datetime.timezone.utc).isoformat())
        )
        await db.commit()

async def log_transfer(type: str, from_user: Optional[str], to_user: Optional[str], amount: float, balance: float) -> None:
    """
    Log a deposit/withdrawal/transfer atomically.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO transfers(type, from_user, to_user, amount, balance, timestamp) VALUES (?, ?, ?, ?, ?, ?) ",
            (type, from_user, to_user, amount, balance,
             datetime.datetime.now(datetime.timezone.utc).isoformat())
        )
        await db.commit()


# Resolution operations
async def resolve_market(market_id: str, correct: str) -> tuple[str, float, float, float]:
    """
    Atomically resolves a market:
      • Marks it resolved in market_data
      • Credits $1 per correct share to each user
      • Logs each resolution
    Returns (question, implied_odds, total_paid, total_lost_shares).
    Raises ValueError on missing or already-resolved market.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        # Fetch state
        cur = await db.execute(
            "SELECT d.resolved, i.question, d.implied_odds "
            "FROM market_data d "
            "JOIN market_info i USING(market_id) "
            "WHERE d.market_id = ?",
            (market_id,)
        )
        row = await cur.fetchone()
        if not row:
            raise ValueError(f"Market `{market_id}` not found")
        was_resolved, question, implied = row
        if was_resolved:
            raise ValueError(f"Market `{market_id}` already resolved")

        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Mark market resolved
        await db.execute(
            "UPDATE market_data "
            "SET resolved=1, resolution=?, resolution_date=? "
            "WHERE market_id=?",
            (correct, ts, market_id)
        )

        # Payout each user and log
        cur = await db.execute(
            "SELECT user_id, outcome, shares "
            "FROM user_bets WHERE market_id=?",
            (market_id,)
        )
        total_paid = 0.0
        total_lost  = 0.0

        async for user_id, outcome, shares in cur:
            # HALF case: pay out $0.50 to everyone
            if correct == "HALF":
                redeemed = 0.5 * shares
            else:
                redeemed = shares if outcome == correct else 0.0
                total_paid += redeemed
                if outcome != correct:
                    total_lost += shares

            # Credit winner (or credit $0 for losers)
            await db.execute(
                "UPDATE user_balances "
                "SET balance = balance + ? "
                "WHERE user_id = ?",
                (redeemed, user_id)
            )
            # Log the resolution row
            await db.execute(
                "INSERT INTO resolutions "
                "(user_id, market_id, outcome, shares, redeemed, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, market_id, outcome, shares, redeemed, ts)
            )

        # Commit once
        await db.commit()
    return question, implied, total_paid, total_lost