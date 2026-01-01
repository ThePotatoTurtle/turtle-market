# TurtleMarket - A Discord Prediction Market Bot

A lightweight, Discord-based prediction market platform for small groups. Powered by a centralized Automated Market Maker (AMM) using the **Logarithmic Market Scoring Rule (LMSR)**, this bot lets you create, trade, and resolve YES/NO markets entirely within Discord.

---

## 🚀 Features

- **Create Markets**: `/create_market` lets admins set up new YES/NO markets with custom market IDs, bet topic, details and conditions, and LMSR liquidity parameter **b**.
- **View Markets**: `/markets` lists all active markets. `/resolved` lists markets already resolved. `/details <id>` shows more information about a specific market. 
- **Trade**:
  - **Buy**: `/buy <id> <Y|N> <amount>` spends dollars to purchase YES/NO shares from the market (AMM).
  - **Sell**: `/sell <id> <Y|N> <percent>` sells a percentage of your YES/NO shares back to the market (AMM).
- **Portfolio**:
  - `/cash` shows your current cash balance.
  - `/port` shows cash, open bets, and total portfolio value.
- **Transfers**: Admins can `/deposit` and `/withdraw` to top up or withdraw funds, respectively. `/send <@user> <amount>` allows users to send cash to each other. 
- **Resolution**: Admins run `/resolve <id> <Y|H|N>` to resolve a market. Winners get \$1 per share, losers get \$0.
- **Help**: `/help` displays all non-admin commands.

---

## 📐 LMSR AMM

LMSR provides continuous pricing via a convex cost function, avoiding order books. Key formulas:

1. **Cost Function**

   `C(q_Y, q_N) = b * ln(exp(q_Y/b) + exp(q_N/b))`

   - **q_Y, q_N**: total YES/NO shares sold
   - **b**: liquidity parameter (higher = more liquidity, less slippage)

2. **Marginal Price**

   `P_YES = exp(q_Y/b) / (exp(q_Y/b) + exp(q_N/b))`
   
   `P_NO = 1 - P_YES`

3. **Buying $A**: solves for Δq such that

   `C(q_Y+Δq, q_N) - C(q_Y, q_N) = A`

   giving you Δq shares for $A.

4. **Selling**: you earn

   `C(q_Y, q_N) - C(q_Y-Δq, q_N)`

   by returning Δq shares.

This design ensures **instant liquidity**, **bounded loss for the MM**, and **smooth price changes** even for erratic markets.

---

## 🛠 Installation & Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/ThePotatoTurtle/turtle-market.git
   ```
2. **Create a Python virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate   # macOS/Linux
   .\venv\Scripts\activate  # Windows
   ```
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure**
   - Create an `.env` file with the following (see ⚙️ Configuration below)
   ```
   DISCORD_TOKEN=
   ADMIN_ID=
   ```
   - In `config.py`, set the mandatory variables `BROADCAST_CHANNEL_ID` and `MARKETS_CHANNEL_ID`, as well as any optional variables.
5. **Run the bot**
   ```bash
   python main.py
   ```

---

## ⚙️ Configuration

| Variable                       | Description                                              |
| -------------------------------|--------------------------------------------------------- |
| `.env.ADMIN_ID`                | **Your Discord user ID (only you can admin markets)**    |
| `.env.DISCORD_TOKEN`           | ** Bot token from the Discord Developer Portal**         |
| `config.DEFAULT_USER_BALANCE`  | Starting balance for users                               |
| `config.POOL_ID`               | ID string representing the AMM pool                      |
| `config.DEFAULT_B`             | Default LMSR **b** liquidity parameter (default `25.0`)  |
| `config.REDEEM_FEE`            | Redemption fee (default `0.05` for 5%)                   |
| `config.BROADCAST_CHANNEL_ID`  | **Channel ID for broadcasting trades**                   |
| `config.MARKETS_CHANNEL_ID`    | **Channel ID for broadcasting new markets & resolutions**|

---

## 📋 Command Reference

### User Commands (public)

- `/markets` — list active markets (ID, question, implied odds)
- `/details <id>` — show detailed info on a market
- `/buy <id> <Y|N> <amount>` — buy YES/NO shares by dollar amount
- `/sell <id> <Y|N> <percent>` — sell percentage of your YES/NO shares
- `/cash` — view your cash balance
- `/port` — view your portfolio
- `/send <@user> <amount>` — transfer cash to another user
- `/resolved` — list all resolved markets
- `/help` — list public commands and descriptions

### Admin Commands

- `/create_market` — create a new market
- `/delete_market` — delete a market
- `/deposit` — credit a user
- `/withdraw` — debit a user
- `/resolve <id> <Y|H|N>` — resolve and pay out a market

---
