import json
import os
import config


# Path to the JSON file storing markets
BASE = os.path.dirname(__file__)
MARKETS_FILE = os.path.join(BASE, 'markets.json')
BALANCES_FILE = os.path.join(BASE, 'user_balances.json')
BETS_FILE = os.path.join(BASE, 'user_bets.json')


# Storage helpers - Markets

def load_markets():
    """
    Load the markets from the JSON file. Returns a dict of market_id -> market_data.
    """
    if not os.path.exists(MARKETS_FILE):
        return {}
    with open(MARKETS_FILE, 'r') as f:
        return json.load(f)

def save_markets(markets):
    """
    Persist the given markets dict to the JSON file.
    """
    with open(MARKETS_FILE, 'w') as f:
        json.dump(markets, f, indent=2)

def create_market(
    market_id: str,
    question: str,
    outcomes=('YES', 'NO'),
    subject=None,
    creator_id=None,
    b=config.DEFAULT_B,
    resolution_date=None
) -> str:
    """
    Create a new binary market with the given public market_id and parameters.
    Raises ValueError if the market_id already exists.
    Returns the market_id on success.
    """
    markets = load_markets()
    if market_id in markets:
        raise ValueError(f"Market ID '{market_id}' already exists")

    markets[market_id] = {
        'question': question,
        'outcomes': list(outcomes),
        'subject': subject,
        'creator': creator_id,
        'b': b,
        'shares': {outcome: 0 for outcome in outcomes},
        'resolved': False,
        'resolution': None,
        'resolution_date': resolution_date,  # 'YYYY-MM-DD'
        'implied_odds': 50.00
    }
    save_markets(markets)
    return market_id

def delete_market(market_id: str) -> None:
    """
    Delete an existing market. Raises ValueError if the market_id does not exist.
    """
    markets = load_markets()
    if market_id not in markets:
        raise ValueError(f"Market ID '{market_id}' does not exist")
    del markets[market_id]
    save_markets(markets)


# Storage helpers - Balances

def load_balances():
    if not os.path.exists(BALANCES_FILE):
        return {}
    with open(BALANCES_FILE, 'r') as f:
        return json.load(f)

def save_balances(balances):
    with open(BALANCES_FILE, 'w') as f:
        json.dump(balances, f, indent=2)

def ensure_balance(user_id: str):
    balances = load_balances()
    if user_id not in balances:
        # AMM pool starts at 0, real users get default
        balances[user_id] = 0.0 if user_id == config.POOL_ID else config.DEFAULT_USER_BALANCE
        save_balances(balances)
    return balances[user_id]

def get_balance(user_id: str) -> float:
    bal = load_balances()
    return ensure_balance(user_id)

def update_balance(user_id: str, delta: float):
    """
    Add delta to user_id’s balance (and initialize if missing).
    """
    balances = load_balances()

    # Initialize missing users (pool or real user) in this same dict
    if user_id not in balances:
        balances[user_id] = (
            0.0 if user_id == config.POOL_ID 
            else config.DEFAULT_USER_BALANCE
        )

    balances[user_id] += delta
    save_balances(balances)


# Storage helpers - Bets

def load_bets():
    if not os.path.exists(BETS_FILE):
        return {}
    with open(BETS_FILE, 'r') as f:
        return json.load(f)

def save_bets(bets):
    with open(BETS_FILE, 'w') as f:
        json.dump(bets, f, indent=2)

def add_bet(user_id: str, market_id: str, outcome: str, shares: float):
    bets = load_bets()
    user = bets.setdefault(user_id, {})
    pos  = user.setdefault(market_id, {'YES': 0.0, 'NO': 0.0})
    pos[outcome] += shares
    save_bets(bets)