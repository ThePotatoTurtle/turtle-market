import json
import os

# Path to the JSON file storing markets
MARKETS_FILE = os.path.join(os.path.dirname(__file__), 'markets.json')

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
    b=100
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
        'resolution': None
    }
    save_markets(markets)
    return market_id
