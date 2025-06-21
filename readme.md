# TurtleMarket - A Discord Prediction Market Bot

A lightweight, Discord-based prediction market platform for small groups. Powered by a centralized Automated Market Maker (AMM) using the **Logarithmic Market Scoring Rule (LMSR)**, this bot lets you create, trade, and resolve YES/NO markets entirely within Discord.

---

## 🚀 Features

- **Create Markets**: `/create_market` lets admins set up new YES/NO markets with custom market IDs, bet topic, details and bet conditions, optional subject-lock, and LMSR liquidity parameter **b**.
- **View Markets**: `/markets` lists all active markets. `/resolved` lists markets already resolved. `/details <id>` shows more information about specific markets. 
- **Trade**:
  - **Buy**: `/buy <id> <Y|N> <amount>` spends dollars to purchase shares from the market (AMM).
  - **Sell**: `/sell <id> <Y|N> <percent>` sells a percentage of your holding back to the market (AMM).
- **Portfolio & Cash**:
  - `/cash` shows your current cash balance.
  - `/port` shows cash, open bets, and total portfolio value.
- **Transfers**: `/send <@user> <amount>` allows users to send cash to each other. Admins can `/deposit` and `/withdraw` to top up or withdraw funds.
- **Resolution**: Admins run `/resolve <id> <Y|N>` to resolve a market. Winners get \$1 per share, losers get \$0.
- **Help**: `/help` displays all non-admin commands.

---

## 📐 How It Works: LMSR AMM

LMSR provides continuous pricing via a convex cost function, avoiding order books. Key formulas:

1. **Cost Function**

   $$
   C(q_Y, q_N) = b \cdot \ln\bigl(e^{q_Y/b} + e^{q_N/b}\bigr)
   $$

   - **q\_Y, q\_N**: total YES/NO shares sold
   - **b**: liquidity parameter (higher = more liquidity, less slippage)

2. **Marginal Price**

   $$
   P_{YES} = \frac{e^{q_Y/b}}{e^{q_Y/b} + e^{q_N/b}},
   \quad P_{NO} = 1 - P_{YES}
   $$

3. **Buying \$A**: solves for Δq such that

   $$
   C(q_Y+Δq,\,q_N) - C(q_Y,\,q_N) = A
   $$

   giving you Δq shares for \$A.

4. **Selling**: you earn

   $$
   C(q_Y,\,q_N) - C(q_Y-Δq,\,q_N)
   $$

   by returning Δq shares.

This design ensures **instant liquidity**, **bounded loss**, and **smooth price adjustments** as volume grows.

---

## 🛠 Installation & Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/ThePotatoTurtle/turtle-market.git
   cd turtle-market
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
   - Copy `.env.example` to `.env` and set your Discord `DEV_GUILD_ID`, `ADMIN_ID`, `DISCORD_TOKEN`.
   - In `config.py`, set `MARKETS_CHANNEL_ID` and `BROADCAST_CHANNEL_ID` for public broadcasts, `POOL_ID` (default `'AMM'`), `DEFAULT_B` for default b-value, and `REDEEM_FEE` for redemption fee.
5. **Run the bot**
   ```bash
   python main.py
   ```

---

## ⚙️ Configuration

| Variable                       | Description                                              |
| -------------------------------|--------------------------------------------------------- |
| `DEV_GUILD_ID`                 | (Optional) Guild ID for command registration in dev only |
| `ADMIN_ID`                     | Your Discord user ID (only you can admin markets)        |
| `DISCORD_TOKEN`                | Bot token from the Discord Developer Portal              |
| `config.BROADCAST_CHANNEL_ID`  | Channel ID for broadcasting trades                       |
| `config.MARKETS_CHANNEL_ID`    | Channel ID for broadcasting new markets & resolution     |
| `config.POOL_ID`               | User ID string representing the AMM pool                 |
| `config.DEFAULT_B`             | Default LMSR **b** liquidity parameter (e.g. `25.0`)     |
| `config.REDEEM_FEE`            | Fractional fee (e.g. `0.01` for 1%) on redemption        |

---

## 📋 Command Reference

### User Commands (public)

- `/markets` — list active markets (ID, question, implied odds of YES)
- `/details <id>` — show full market info
- `/buy <id> <Y|N> <amount>` — buy YES/NO shares by dollar amount
- `/sell <id> <Y|N> <percent>` — sell percentage of your position
- `/cash` — view your cash balance
- `/port` — view your portfolio
- `/send <@user> <amount>` — transfer cash to another user
- `/resolved` — list all resolved markets
- `/help` — list public commands and descriptions

### Admin Commands (prefix: **Admin:**\* )

- `/create_market` — create a new market
- `/delete_market` — delete a market
- `/deposit` — credit a use
- `/withdraw` — debit a user
- `/resolve <id> <Y|N>` — resolve and pay out a market

---