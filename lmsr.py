import math


def lmsr_cost(q_yes: float, q_no: float, b: float) -> float:
    """
    Stable LMSR cost function for binary outcomes:
    C(q_yes, q_no) = b * log(e^(q_yes/b) + e^(q_no/b)), computed via log-sum-exp for numerical stability.
    """
    x = q_yes / b
    y = q_no / b
    m = max(x, y)
    # log-sum-exp: log(e^x + e^y) = m + log(e^(x-m) + e^(y-m))
    return b * (m + math.log(math.exp(x - m) + math.exp(y - m)))


def lmsr_price(q_yes: float, q_no: float, b: float) -> float:
    """
    Stable implied probability (price) for the YES outcome via softmax.
    p_yes = e^(q_yes/b) / (e^(q_yes/b) + e^(q_no/b))
    """
    x = q_yes / b
    y = q_no / b
    m = max(x, y)
    ex = math.exp(x - m)
    ey = math.exp(y - m)
    return ex / (ex + ey)


def calc_shares(delta_cash: float, q_yes: float, q_no: float, b: float,
                side: str, tol: float = 1e-6, max_iter: int = 100) -> float:
    """
    Given a cash amount (delta_cash) to spend on 'YES' or 'NO',
    compute the number of shares (delta_q) such that:
      C(q + delta_q) - C(q) = delta_cash
    Uses binary search on delta_q with stable cost computation.

    Parameters:
    - delta_cash: amount of money to spend
    - q_yes, q_no: current total shares
    - b: LMSR liquidity parameter
    - side: 'YES' or 'NO'
    """
    # Current cost
    current_cost = lmsr_cost(q_yes, q_no, b)
    target = current_cost + delta_cash

    # Establish initial search bounds
    low, high = 0.0, max(delta_cash / b * b, 1.0)
    # Expand high bound until cost(high) >= target
    while True:
        if side.upper() == 'YES':
            c = lmsr_cost(q_yes + high, q_no, b)
        else:
            c = lmsr_cost(q_yes, q_no + high, b)
        if c >= target:
            break
        high *= 2

    # Binary search
    for _ in range(max_iter):
        mid = (low + high) / 2
        if side.upper() == 'YES':
            c_mid = lmsr_cost(q_yes + mid, q_no, b)
        else:
            c_mid = lmsr_cost(q_yes, q_no + mid, b)

        if abs(c_mid - target) < tol:
            return mid
        if c_mid > target:
            high = mid
        else:
            low = mid

    # Return approximation if tol not met
    return (low + high) / 2