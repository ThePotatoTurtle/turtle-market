import os, aiosqlite, datetime
from typing import Dict, Any, Optional
import config

# Paths to the SQLite database files
BASE = os.path.dirname(__file__)
DB_DIR = os.path.join(BASE, 'data')
os.makedirs(DB_DIR, exist_ok=True)  # Ensure the folder exists

MARKETS_DB   = os.path.join(DB_DIR, 'markets.db')
BALANCES_DB  = os.path.join(DB_DIR, 'user_balances.db')
BETS_DB      = os.path.join(DB_DIR, 'user_bets.db')
TRADES_DB    = os.path.join(DB_DIR, 'trades.db')
RESOLVED_DB  = os.path.join(DB_DIR, 'resolutions.db')
TRANSFERS_DB = os.path.join(DB_DIR, 'transfers.db')

# Initialization

async def init_markets_db():
    async with aiosqlite.connect(MARKETS_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS market_info (
                market_id   TEXT PRIMARY KEY,
                question    TEXT NOT NULL,
                details     TEXT,
                b           REAL    NOT NULL,
                subject     TEXT,
                creator_id  TEXT
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS market_data (
                market_id       TEXT    PRIMARY KEY,
                yes_shares      REAL    NOT NULL DEFAULT 0,
                no_shares       REAL    NOT NULL DEFAULT 0,
                resolved        INTEGER NOT NULL DEFAULT 0,
                resolution      TEXT,
                resolution_date TEXT,
                implied_odds    REAL    DEFAULT 0.5,
                last_trade      DATETIME,
                volume_traded   REAL    DEFAULT 0,
                FOREIGN KEY(market_id) REFERENCES market_info(market_id)
            )""")
        await db.commit()

async def init_balances_db():
    async with aiosqlite.connect(BALANCES_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS balances (
                user_id TEXT PRIMARY KEY,
                balance REAL    NOT NULL
            )""")
        await db.commit()

async def init_bets_db():
    async with aiosqlite.connect(BETS_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bets (
                user_id     TEXT    NOT NULL,
                market_id   TEXT    NOT NULL,
                outcome     TEXT    NOT NULL,
                shares      REAL    NOT NULL,
                cost_basis  REAL    DEFAULT 0,
                last_trade  DATETIME,
                PRIMARY KEY(user_id, market_id, outcome)
            )""")
        await db.commit()

async def init_trades_db():
    async with aiosqlite.connect(TRADES_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT    NOT NULL,
                market_id  TEXT    NOT NULL,
                outcome    TEXT    NOT NULL,
                shares     REAL    NOT NULL,
                amount     REAL    NOT NULL,
                price      REAL    NOT NULL,
                balance    REAL    NOT NULL,
                timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        await db.commit()

async def init_resolved_db():
    async with aiosqlite.connect(RESOLVED_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS resolved (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT    NOT NULL,
                market_id  TEXT    NOT NULL,
                outcome    TEXT    NOT NULL,
                shares     REAL    NOT NULL,
                redeemed   REAL    NOT NULL,
                timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        await db.commit()

async def init_transfers_db():
    async with aiosqlite.connect(TRANSFERS_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transfers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                type       TEXT    NOT NULL,
                from_user  TEXT,
                to_user    TEXT,
                amount     REAL    NOT NULL,
                balance    REAL    NOT NULL,
                timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        await db.commit()

async def init_db():
    """Initialize all SQLite databases at startup."""
    await init_markets_db()
    await init_balances_db()
    await init_bets_db()
    await init_trades_db()
    await init_resolved_db()
    await init_transfers_db()


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
    async with aiosqlite.connect(MARKETS_DB) as db:
        # Prevent duplicates
        cursor = await db.execute("SELECT 1 FROM market_info WHERE market_id = ?", (market_id,))
        if await cursor.fetchone():
            raise ValueError(f"Market ID '{market_id}' already exists")
        # Insert static info
        await db.execute(
            "INSERT INTO market_info(market_id, question, details, b, subject, creator_id) VALUES (?, ?, ?, ?, ?, ?)",
            (market_id, question, details, b, subject, creator_id)
        )
        # Initialize live data
        await db.execute("INSERT INTO market_data(market_id) VALUES (?)", (market_id,))
        await db.commit()

async def load_markets() -> Dict[str, Dict[str, Any]]:
    async with aiosqlite.connect(MARKETS_DB) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT i.market_id, i.question, i.details, i.b, i.subject, i.creator_id,"
            " d.yes_shares, d.no_shares, d.resolved, d.resolution, d.resolution_date,"
            " d.implied_odds, d.last_trade, d.volume_traded"
            " FROM market_info i"
            " JOIN market_data d ON i.market_id = d.market_id"
        )
        markets: Dict[str, Dict[str, Any]] = {}
        rows = await cursor.fetchall()
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
    async with aiosqlite.connect(MARKETS_DB) as db:
        for mid, data in markets.items():
            # Update static info
            await db.execute(
                "UPDATE market_info SET question=?, details=?, b=?, subject=?, creator_id=? WHERE market_id=?",
                (
                    data['question'], data['details'], data['b'], data['subject'], data['creator'],
                    mid
                )
            )
            # Update live data
            await db.execute(
                "UPDATE market_data SET yes_shares=?, no_shares=?, resolved=?, resolution=?, resolution_date=?, implied_odds=?, last_trade=?, volume_traded=? WHERE market_id=?",
                (
                    data['shares']['YES'], data['shares']['NO'], int(data['resolved']),
                    data['resolution'], data['resolution_date'], data['implied_odds'],
                    data['last_trade'], data['volume_traded'], mid
                )
            )
        await db.commit()

async def delete_market(market_id: str) -> None:
    async with aiosqlite.connect(MARKETS_DB) as db:
        await db.execute("DELETE FROM market_data WHERE market_id=?", (market_id,))
        await db.execute("DELETE FROM market_info WHERE market_id=?", (market_id,))
        await db.commit()


# Balance operations

async def get_balance(user_id: str) -> float:
    async with aiosqlite.connect(BALANCES_DB) as db:
        cursor = await db.execute("SELECT balance FROM balances WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return row[0]
        bal = config.DEFAULT_USER_BALANCE
        await db.execute("INSERT INTO balances(user_id, balance) VALUES (?, ?)", (user_id, bal))
        await db.commit()
        return bal

async def update_balance(user_id: str, delta: float) -> None:
    bal = await get_balance(user_id)
    async with aiosqlite.connect(BALANCES_DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO balances(user_id, balance) VALUES (?, ?)",
            (user_id, bal + delta)
        )
        await db.commit()


# Bets operations

async def load_bets() -> Dict[str, Dict[str, dict]]:
    async with aiosqlite.connect(BETS_DB) as db:
        cursor = await db.execute("SELECT user_id, market_id, outcome, shares, cost_basis, last_trade FROM bets")
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
    bets = await load_bets()
    current_bet = bets.get(user_id, {}).get(market_id, {}).get(outcome, {'shares': 0.0, 'cost_basis': 0.0})
    current_shares = current_bet.get('shares', 0.0)
    current_cost   = current_bet.get('cost_basis', 0.0)
    new_shares = current_shares + delta_shares
    new_cost   = current_cost + delta_cost
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    async with aiosqlite.connect(BETS_DB) as db:
        if new_shares <= 0:
            await db.execute(
                "DELETE FROM bets WHERE user_id=? AND market_id=? AND outcome=?",
                (user_id, market_id, outcome)
            )
        else:
            await db.execute(
                "INSERT OR REPLACE INTO bets(user_id, market_id, outcome, shares, cost_basis, last_trade) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, market_id, outcome, new_shares, new_cost, now)
            )
        await db.commit()


# Transaction logging

async def log_trade(user_id: str, market_id: str, outcome: str, shares: float, amount: float, price: float, balance: float) -> None:
    async with aiosqlite.connect(TRADES_DB) as db:
        await db.execute(
            "INSERT INTO trades (user_id, market_id, outcome, shares, amount, price, balance) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, market_id, outcome, shares, amount, price, balance)
        )
        await db.commit()

async def log_resolve(user_id: str, market_id: str, outcome: str, shares: float, redeemed: float) -> None:
    async with aiosqlite.connect(RESOLVED_DB) as db:
        await db.execute(
            "INSERT INTO resolved (user_id, market_id, outcome, shares, redeemed) VALUES (?, ?, ?, ?, ?)",
            (user_id, market_id, outcome, shares, redeemed)
        )
        await db.commit()

async def log_transfer(type: str, from_user: Optional[str], to_user: Optional[str], amount: float, balance: float) -> None:
    async with aiosqlite.connect(TRANSFERS_DB) as db:
        await db.execute(
            "INSERT INTO transfers (type, from_user, to_user, amount, balance) VALUES (?, ?, ?, ?, ?)",
            (type, from_user, to_user, amount, balance)
        )
        await db.commit()
