-- schema.sql
-- This script creates all 8 tables in a single database: market_info, market_data,
-- resolutions, trades, transfers, user_balances, user_bets, sqlite_sequence (managed by SQLite).

PRAGMA foreign_keys = ON;

-- 1. Market information (metadata)
CREATE TABLE IF NOT EXISTS market_info (
    market_id       TEXT    PRIMARY KEY,
    question        TEXT    NOT NULL,
    details         TEXT,
    b               REAL    NOT NULL,
    subject         TEXT,
    creator_id      TEXT
);

-- 2. Market data (shares, status, etc.)
CREATE TABLE IF NOT EXISTS market_data (
    market_id       TEXT    PRIMARY KEY,
    yes_shares      REAL    NOT NULL DEFAULT 0,
    no_shares       REAL    NOT NULL DEFAULT 0,
    resolved        INTEGER NOT NULL DEFAULT 0,
    resolution      TEXT,
    resolution_date TEXT,
    implied_odds    REAL    DEFAULT 0.5,
    last_trade      TEXT,      -- ISO-8601 string
    volume_traded   REAL    DEFAULT 0,
    FOREIGN KEY(market_id) REFERENCES market_info(market_id) ON DELETE CASCADE
);

-- 3. Resolution logs
CREATE TABLE IF NOT EXISTS resolutions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT    NOT NULL,
    market_id  TEXT    NOT NULL,
    outcome    TEXT    NOT NULL,
    shares     REAL    NOT NULL,
    redeemed   REAL    NOT NULL,
    timestamp  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(market_id) REFERENCES market_info(market_id)
);

-- 4. Trade logs (buys/sells)
CREATE TABLE IF NOT EXISTS trades (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT    NOT NULL,
    market_id  TEXT    NOT NULL,
    outcome    TEXT    NOT NULL,
    shares     REAL    NOT NULL,
    amount     REAL    NOT NULL,
    price      REAL    NOT NULL,
    balance    REAL    NOT NULL,
    timestamp  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(market_id) REFERENCES market_info(market_id)
);

-- 5. Transfer logs (deposits, withdrawals, sends)
CREATE TABLE IF NOT EXISTS transfers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT     NOT NULL,
    from_user  TEXT,
    to_user    TEXT,
    amount     REAL     NOT NULL,
    balance    REAL     NOT NULL,
    timestamp  TEXT     NOT NULL DEFAULT (datetime('now'))
);

-- 6. User balances and records
CREATE TABLE IF NOT EXISTS user_balances (
    user_id     TEXT    PRIMARY KEY,
    balance     REAL    NOT NULL,
    volume_traded   REAL    NOT NULL DEFAULT 0,
    volume_resolved REAL    NOT NULL DEFAULT 0
);

-- 7. User bets (portfolio)
CREATE TABLE IF NOT EXISTS user_bets (
    user_id     TEXT    NOT NULL,
    market_id   TEXT    NOT NULL,
    outcome     TEXT    NOT NULL,
    shares      REAL    NOT NULL,
    cost_basis  REAL    DEFAULT 0,
    last_trade  TEXT,
    PRIMARY KEY(user_id, market_id, outcome),
    FOREIGN KEY(market_id) REFERENCES market_info(market_id)
);

-- 8. sqlite_sequence is maintained by SQLite to track AUTOINCREMENT values.
--    No need to create it manually; SQLite creates it when needed.

-- Ensure foreign key constraints are enforced
PRAGMA foreign_keys = ON;