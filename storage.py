import os, sqlite3
from typing import Dict, Any, Optional
import config

# Paths to the SQLite database files
BASE = os.path.dirname(__file__)
DB_DIR = os.path.join(BASE, 'database')
os.makedirs(DB_DIR, exist_ok=True)  # Ensure the folder exists
MARKETS_DB  = os.path.join(DB_DIR, 'markets.db')
BALANCES_DB = os.path.join(DB_DIR, 'user_balances.db')
BETS_DB     = os.path.join(DB_DIR, 'user_bets.db')

# Initialization

def init_markets_db():
    conn = sqlite3.connect(MARKETS_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS markets (
            market_id        TEXT PRIMARY KEY,
            question         TEXT    NOT NULL,
            b                REAL    NOT NULL,
            subject          TEXT,
            creator_id       TEXT,
            resolved         INTEGER NOT NULL DEFAULT 0,
            resolution       TEXT,
            resolution_date  TEXT,
            implied_odds     REAL    DEFAULT 0.5
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS market_shares (
            market_id TEXT    NOT NULL,
            outcome   TEXT    NOT NULL,
            shares    REAL    NOT NULL,
            PRIMARY KEY(market_id, outcome),
            FOREIGN KEY(market_id) REFERENCES markets(market_id)
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
            user_id   TEXT    NOT NULL,
            market_id TEXT    NOT NULL,
            outcome   TEXT    NOT NULL,
            shares    REAL    NOT NULL,
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
    subject: Optional[str] = None,
    creator_id: Optional[str] = None,
    b: float = config.DEFAULT_B,
    resolution_date: Optional[str] = None
) -> None:
    conn = sqlite3.connect(MARKETS_DB)
    c = conn.cursor()
    # Prevent duplicates
    c.execute("SELECT 1 FROM markets WHERE market_id = ?", (market_id,))
    if c.fetchone():
        conn.close()
        raise ValueError(f"Market ID '{market_id}' already exists")

    c.execute(
        "INSERT INTO markets(market_id, question, b, subject, creator_id, resolution_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (market_id, question, b, subject, creator_id, resolution_date)
    )
    # Initialize share counts
    for o in outcomes:
        c.execute(
            "INSERT INTO market_shares(market_id, outcome, shares) VALUES (?, ?, 0)",
            (market_id, o)
        )
    conn.commit()
    conn.close()

def load_markets() -> Dict[str, Dict[str, Any]]:
    conn = sqlite3.connect(MARKETS_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM markets")
    markets: Dict[str, Dict[str, Any]] = {}
    for row in c.fetchall():
        markets[row['market_id']] = {
            'question': row['question'],
            'b': row['b'],
            'subject': row['subject'],
            'creator': row['creator_id'],
            'resolved': bool(row['resolved']),
            'resolution': row['resolution'],
            'resolution_date': row['resolution_date'],
            'implied_odds': row['implied_odds'],
            'shares': {}
        }

    c.execute("SELECT market_id, outcome, shares FROM market_shares")
    for mid, outcome, shares in c.fetchall():
        if mid in markets:
            markets[mid]['shares'][outcome] = shares

    conn.close()
    return markets

def save_markets(markets: Dict[str, Dict[str, Any]]) -> None:
    conn = sqlite3.connect(MARKETS_DB)
    c = conn.cursor()
    for mid, data in markets.items():
        c.execute(
            "UPDATE markets SET question=?, b=?, subject=?, creator_id=?, "
            "resolved=?, resolution=?, resolution_date=?, implied_odds=? "
            "WHERE market_id=?",
            (
                data['question'], data['b'], data['subject'], data['creator'],
                int(data.get('resolved', False)), data.get('resolution'),
                data.get('resolution_date'), data.get('implied_odds', 0.5), mid
            )
        )
        for outcome, sh in data['shares'].items():
            c.execute(
                "UPDATE market_shares SET shares=? WHERE market_id=? AND outcome=?",
                (sh, mid, outcome)
            )
    conn.commit()
    conn.close()

def delete_market(market_id: str) -> None:
    conn = sqlite3.connect(MARKETS_DB)
    c = conn.cursor()
    c.execute("DELETE FROM market_shares WHERE market_id=?", (market_id,))
    c.execute("DELETE FROM markets WHERE market_id=?", (market_id,))
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
            "INSERT INTO balances(user_id, balance) VALUES (?, ?)",
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
    c.execute("SELECT user_id, market_id, outcome, shares FROM bets")
    bets: Dict[str, Dict[str, float]] = {}
    for user_id, mid, outcome, shares in c.fetchall():
        user = bets.setdefault(user_id, {})
        pos = user.setdefault(mid, {'YES': 0.0, 'NO': 0.0})
        pos[outcome] = shares
    conn.close()
    return bets

def add_bet(user_id: str, market_id: str, outcome: str, delta_shares: float) -> None:
    bets = load_bets().get(user_id, {})
    current = bets.get(market_id, {}).get(outcome, 0.0)
    new_val = current + delta_shares
    conn = sqlite3.connect(BETS_DB)
    c = conn.cursor()
    if new_val <= 0:
        c.execute(
            "DELETE FROM bets WHERE user_id=? AND market_id=? AND outcome=?",
            (user_id, market_id, outcome)
        )
    else:
        c.execute(
            "INSERT OR REPLACE INTO bets(user_id, market_id, outcome, shares) "
            "VALUES (?, ?, ?, ?)",
            (user_id, market_id, outcome, new_val)
        )
    conn.commit()
    conn.close()

    