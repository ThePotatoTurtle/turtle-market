import os, sqlite3, datetime
from typing import Dict, Any, Optional
import config

# Paths to the SQLite database files
BASE = os.path.dirname(__file__)
DB_DIR = os.path.join(BASE, 'data')
os.makedirs(DB_DIR, exist_ok=True)  # Ensure the folder exists
MARKETS_DB  = os.path.join(DB_DIR, 'markets.db')
BALANCES_DB = os.path.join(DB_DIR, 'user_balances.db')
BETS_DB     = os.path.join(DB_DIR, 'user_bets.db')

# Initialization

def init_markets_db():
    conn = sqlite3.connect(MARKETS_DB)
    c = conn.cursor()
    # Static market info
    c.execute("""
        CREATE TABLE IF NOT EXISTS market_info (
            market_id   TEXT PRIMARY KEY,
            question    TEXT NOT NULL,
            details     TEXT,
            b           REAL NOT NULL,
            subject     TEXT,
            creator_id  TEXT
        )
    """)
    # Live market data
    c.execute("""
        CREATE TABLE IF NOT EXISTS market_data (
            market_id       TEXT PRIMARY KEY,
            yes_shares      REAL    NOT NULL DEFAULT 0,
            no_shares       REAL    NOT NULL DEFAULT 0,
            resolved        INTEGER NOT NULL DEFAULT 0,
            resolution      TEXT,
            resolution_date TEXT,
            implied_odds    REAL    DEFAULT 0.5,
            last_trade      DATETIME,
            volume_traded   REAL    DEFAULT 0,
            FOREIGN KEY(market_id) REFERENCES market_info(market_id)
        )
    """)
    conn.commit()
    conn.close()
    

def init_balances_db():
    conn = sqlite3.connect(BALANCES_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            user_id TEXT PRIMARY KEY,
            balance REAL    NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def init_bets_db():
    conn = sqlite3.connect(BETS_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            user_id     TEXT    NOT NULL,
            market_id   TEXT    NOT NULL,
            outcome     TEXT    NOT NULL,
            shares      REAL    NOT NULL,
            cost_basis  REAL    DEFAULT 0,
            last_trade  DATETIME,
            PRIMARY KEY(user_id, market_id, outcome)
        )
    """)
    conn.commit()
    conn.close()

def init_db():
    """Initialize all SQLite databases at startup."""
    init_markets_db()
    init_balances_db()
    init_bets_db()

# Market operations

def create_market(
    market_id: str,
    question: str,
    outcomes=('YES', 'NO'),
    details: Optional[str] = None,
    subject: Optional[str] = None,
    creator_id: Optional[str] = None,
    b: float = config.DEFAULT_B
) -> None:
    conn = sqlite3.connect(MARKETS_DB)
    c = conn.cursor()
    # Prevent duplicates
    c.execute("SELECT 1 FROM market_info WHERE market_id = ?", (market_id,))
    if c.fetchone():
        conn.close()
        raise ValueError(f"Market ID '{market_id}' already exists")
    # Insert static info
    c.execute(
        "INSERT INTO market_info(market_id, question, details, b, subject, creator_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (market_id, question, details, b, subject, creator_id)
    )
    # Initialize live data
    c.execute(
        "INSERT INTO market_data(market_id) VALUES (?)",
        (market_id,)
    )
    conn.commit()
    conn.close()

def load_markets() -> Dict[str, Dict[str, Any]]:
    conn = sqlite3.connect(MARKETS_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Join info and data
    c.execute(
        "SELECT i.market_id, i.question, i.details, i.b, i.subject, i.creator_id,"
        " d.yes_shares, d.no_shares, d.resolved, d.resolution, d.resolution_date,"
        " d.implied_odds, d.last_trade, d.volume_traded"
        " FROM market_info i"
        " JOIN market_data d ON i.market_id = d.market_id"
    )
    markets: Dict[str, Dict[str, Any]] = {}
    for row in c.fetchall():
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
    conn.close()
    return markets

def save_markets(markets: Dict[str, Dict[str, Any]]) -> None:
    conn = sqlite3.connect(MARKETS_DB)
    c = conn.cursor()
    for mid, data in markets.items():
        # Update static info
        c.execute(
            "UPDATE market_info SET question=?, details=?, b=?, subject=?, creator_id=?"
            " WHERE market_id=?",
            (
                data['question'], data['details'], data['b'], data['subject'], data['creator'],
                mid
            )
        )
        # Update live data
        c.execute(
            "UPDATE market_data SET yes_shares=?, no_shares=?, resolved=?, resolution=?,"
            " resolution_date=?, implied_odds=?, last_trade=?, volume_traded=?"
            " WHERE market_id=?",
            (
                data['shares']['YES'], data['shares']['NO'], int(data['resolved']),
                data['resolution'], data['resolution_date'], data['implied_odds'],
                data['last_trade'], data['volume_traded'], mid
            )
        )
    conn.commit()
    conn.close()

def delete_market(market_id: str) -> None:
    conn = sqlite3.connect(MARKETS_DB)
    c = conn.cursor()
    c.execute("DELETE FROM market_data WHERE market_id=?", (market_id,))
    c.execute("DELETE FROM market_info WHERE market_id=?", (market_id,))
    conn.commit()
    conn.close()

# Balance operations

def get_balance(user_id: str) -> float:
    conn = sqlite3.connect(BALANCES_DB)
    c = conn.cursor()
    c.execute("SELECT balance FROM balances WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        bal = row[0]
    else:
        bal = config.DEFAULT_USER_BALANCE
        c.execute(
            "INSERT INTO balances(user_id, balance) VALUES (?, ?)" ,
            (user_id, bal)
        )
        conn.commit()
    conn.close()
    return bal

def update_balance(user_id: str, delta: float) -> None:
    bal = get_balance(user_id)
    conn = sqlite3.connect(BALANCES_DB)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO balances(user_id, balance) VALUES (?, ?)",
        (user_id, bal + delta)
    )
    conn.commit()
    conn.close()

# Bets operations

def load_bets() -> Dict[str, Dict[str, float]]:
    conn = sqlite3.connect(BETS_DB)
    c = conn.cursor()
    c.execute("SELECT user_id, market_id, outcome, shares, cost_basis, last_trade FROM bets")
    bets: Dict[str, Dict[str, dict]] = {}
    for user_id, mid, outcome, shares, cost_basis, last_trade in c.fetchall():
        user = bets.setdefault(user_id, {})
        pos  = user.setdefault(mid, {'YES': {}, 'NO': {}})
        pos[outcome] = {
            'shares': shares,
            'cost_basis': cost_basis,
            'last_trade': last_trade
        }
    conn.close()
    return bets

def add_bet(
    user_id: str,
    market_id: str,
    outcome: str,
    delta_shares: float,
    delta_cost: float
) -> None:
    # Load current bet info
    bets = load_bets().get(user_id, {})
    current_bet = bets.get(market_id, {}).get(outcome, {'shares': 0.0, 'cost_basis': 0.0})
    current_shares = current_bet.get('shares', 0.0)
    current_cost = current_bet.get('cost_basis', 0.0)
    new_shares = current_shares + delta_shares
    new_cost = current_cost + delta_cost
    now = datetime.datetime.now(datetime.UTC).isoformat()

    conn = sqlite3.connect(BETS_DB)
    c = conn.cursor()
    if new_shares <= 0:
        c.execute(
            "DELETE FROM bets WHERE user_id=? AND market_id=? AND outcome=?",
            (user_id, market_id, outcome)
        )
    else:
        c.execute(
            "INSERT OR REPLACE INTO bets(user_id, market_id, outcome, shares, cost_basis, last_trade) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, market_id, outcome, new_shares, new_cost, now)
        )
    conn.commit()
    conn.close()

    