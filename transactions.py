import os, aiosqlite

# Paths to the SQLite database files
BASE = os.path.dirname(__file__)
DB_DIR = os.path.join(BASE, 'database')
os.makedirs(DB_DIR, exist_ok=True)  # Ensure the folder exists
TRADES_DB      = os.path.join(DB_DIR, "trades.db")
RESOLVED_DB    = os.path.join(DB_DIR, "resolutions.db")
TRANSFERS_DB   = os.path.join(DB_DIR, "transfers.db")




# Initialization

async def init_trades_db():
    async with aiosqlite.connect(TRADES_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT    NOT NULL,
                market_id TEXT NOT NULL,
                outcome TEXT   NOT NULL,
                shares  REAL    NOT NULL,   -- + for buy, - for sell
                amount  REAL    NOT NULL,   -- + spent to buy, - received from sell
                price   REAL    NOT NULL,   -- average price = amount/shares
                balance REAL    NOT NULL,   -- user balance after trade
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def init_resolved_db():
    async with aiosqlite.connect(RESOLVED_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS resolved (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   TEXT    NOT NULL,
                market_id TEXT    NOT NULL,
                outcome   TEXT    NOT NULL,
                shares    REAL    NOT NULL,
                redeemed  REAL    NOT NULL,   -- $ redeemed (0 for wrong outcome)
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def init_transfers_db():
    async with aiosqlite.connect(TRANSFERS_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transfers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                type       TEXT    NOT NULL,   -- deposit, withdrawal, transfer
                from_user  TEXT,               -- NULL for deposit
                to_user    TEXT,               -- NULL for withdrawal
                amount     REAL    NOT NULL,
                balance    REAL    NOT NULL,          
                timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


# Logging functions

async def log_trade(user_id: str, market_id: str, outcome: str, shares: float, amount: float, price: float, balance: float):
    async with aiosqlite.connect(TRADES_DB) as db:
        await db.execute(
            "INSERT INTO trades (user_id, market_id, outcome, shares, amount, price, balance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, market_id, outcome, shares, amount, price, balance)
        )
        await db.commit()

async def log_resolve(user_id: str, market_id: str, outcome: str, shares: float, redeemed: float):
    async with aiosqlite.connect(RESOLVED_DB) as db:
        await db.execute(
            "INSERT INTO resolved (user_id, market_id, outcome, shares, redeemed) VALUES (?, ?, ?, ?, ?)",
            (user_id, market_id, outcome, shares, redeemed)
        )
        await db.commit()

async def log_transfer(type: str, from_user: str, to_user: str, amount: float, balance: float):
    async with aiosqlite.connect(TRANSFERS_DB) as db:
        await db.execute(
            "INSERT INTO transfers (type, from_user, to_user, amount, balance) VALUES (?, ?, ?, ?, ?)",
            (type, from_user, to_user, amount, balance)
        )
        await db.commit()