# test_lmsr.py
# Tests for the LMSR math in lmsr.py: cost function, pricing, and share calculation.
# Run with: pytest test_lmsr.py

import math
import pytest
import lmsr


def direct_cost(q_yes: float, q_no: float, b: float) -> float:
    """Naive LMSR cost formula (overflows for large q/b; used as reference only)."""
    return b * math.log(math.exp(q_yes / b) + math.exp(q_no / b))


class TestLmsrCost:
    def test_zero_state_is_b_ln2(self):
        # C(0, 0) = b * ln(2)
        for b in (1.0, 25.0, 100.0):
            assert lmsr.lmsr_cost(0, 0, b) == pytest.approx(b * math.log(2))

    @pytest.mark.parametrize("q_yes,q_no,b", [
        (0, 0, 100.0),
        (50, 0, 100.0),
        (0, 50, 100.0),
        (30, 70, 25.0),
        (123.4, 56.7, 100.0),
        (5, 3, 1.0),
    ])
    def test_matches_direct_formula(self, q_yes, q_no, b):
        assert lmsr.lmsr_cost(q_yes, q_no, b) == pytest.approx(direct_cost(q_yes, q_no, b))

    def test_symmetry(self):
        # C(x, y) == C(y, x)
        assert lmsr.lmsr_cost(80, 20, 100.0) == pytest.approx(lmsr.lmsr_cost(20, 80, 100.0))

    def test_monotonic_in_shares(self):
        # Cost strictly increases as shares are added
        b = 100.0
        c0 = lmsr.lmsr_cost(0, 0, b)
        c1 = lmsr.lmsr_cost(10, 0, b)
        c2 = lmsr.lmsr_cost(20, 0, b)
        assert c0 < c1 < c2

    def test_no_overflow_for_large_q(self):
        # Regression for commit 1a262a5 (lmsr overflow on large orders).
        # The naive formula overflows here; log-sum-exp must not.
        b = 100.0
        q = 1e7  # q/b = 100000 → e^100000 overflows a float
        with pytest.raises(OverflowError):
            direct_cost(q, 0, b)
        c = lmsr.lmsr_cost(q, 0, b)
        # For q_yes >> q_no, C ≈ q_yes (the max term dominates)
        assert c == pytest.approx(q, rel=1e-9)
        assert math.isfinite(c)


class TestLmsrPrice:
    def test_even_market_is_half(self):
        assert lmsr.lmsr_price(0, 0, 100.0) == pytest.approx(0.5)
        # Equal shares on both sides → 50% regardless of magnitude
        assert lmsr.lmsr_price(500, 500, 25.0) == pytest.approx(0.5)

    @pytest.mark.parametrize("q_yes,q_no,b", [
        (50, 0, 100.0),
        (30, 70, 25.0),
        (123.4, 56.7, 100.0),
    ])
    def test_matches_direct_softmax(self, q_yes, q_no, b):
        expected = math.exp(q_yes / b) / (math.exp(q_yes / b) + math.exp(q_no / b))
        assert lmsr.lmsr_price(q_yes, q_no, b) == pytest.approx(expected)

    def test_yes_and_no_prices_sum_to_one(self):
        # p_no = price with arguments swapped; must complement p_yes
        p_yes = lmsr.lmsr_price(80, 20, 100.0)
        p_no = lmsr.lmsr_price(20, 80, 100.0)
        assert p_yes + p_no == pytest.approx(1.0)

    def test_monotonic_in_q_yes(self):
        b = 100.0
        prices = [lmsr.lmsr_price(q, 50, b) for q in (0, 25, 50, 100, 200)]
        assert all(a < z for a, z in zip(prices, prices[1:]))
        assert all(0.0 < p < 1.0 for p in prices)

    def test_extremes_are_stable(self):
        # Lopsided markets must not overflow and must approach 0/1
        b = 100.0
        assert lmsr.lmsr_price(1e7, 0, b) == pytest.approx(1.0)
        assert lmsr.lmsr_price(0, 1e7, b) == pytest.approx(0.0)


class TestCalcShares:
    @pytest.mark.parametrize("b", [1.0, 25.0, 100.0, 1000.0])
    @pytest.mark.parametrize("side", ["YES", "NO"])
    def test_cost_difference_equals_amount(self, b, side):
        # Defining property: C(q + Δq) - C(q) == amount spent
        q_yes, q_no, amount = 40.0, 60.0, 10.0
        shares = lmsr.calc_shares(amount, q_yes, q_no, b, side)
        if side == "YES":
            new_cost = lmsr.lmsr_cost(q_yes + shares, q_no, b)
        else:
            new_cost = lmsr.lmsr_cost(q_yes, q_no + shares, b)
        assert new_cost - lmsr.lmsr_cost(q_yes, q_no, b) == pytest.approx(amount, abs=1e-5)

    def test_average_price_between_marginal_prices(self):
        # avg price paid must sit between the pre- and post-trade marginal prices
        q_yes, q_no, b, amount = 0.0, 0.0, 100.0, 50.0
        shares = lmsr.calc_shares(amount, q_yes, q_no, b, "YES")
        p_before = lmsr.lmsr_price(q_yes, q_no, b)
        p_after = lmsr.lmsr_price(q_yes + shares, q_no, b)
        avg = amount / shares
        assert p_before < avg < p_after

    def test_buying_yes_moves_price_up(self):
        q_yes, q_no, b = 10.0, 10.0, 100.0
        shares = lmsr.calc_shares(25.0, q_yes, q_no, b, "YES")
        assert lmsr.lmsr_price(q_yes + shares, q_no, b) > lmsr.lmsr_price(q_yes, q_no, b)

    def test_buying_no_moves_price_down(self):
        q_yes, q_no, b = 10.0, 10.0, 100.0
        shares = lmsr.calc_shares(25.0, q_yes, q_no, b, "NO")
        assert lmsr.lmsr_price(q_yes, q_no + shares, b) < lmsr.lmsr_price(q_yes, q_no, b)

    def test_shares_exceed_dollars_spent(self):
        # Marginal price is always < $1, so $A always buys more than A shares
        shares = lmsr.calc_shares(20.0, 50.0, 50.0, 100.0, "YES")
        assert shares > 20.0

    def test_more_cash_buys_more_shares(self):
        args = (30.0, 70.0, 100.0, "YES")
        s1 = lmsr.calc_shares(5.0, *args)
        s2 = lmsr.calc_shares(10.0, *args)
        s3 = lmsr.calc_shares(50.0, *args)
        assert s1 < s2 < s3
        # Convexity: doubling spend buys less than double the shares (price rises)
        assert s2 < 2 * s1

    def test_large_order_triggers_bound_expansion(self):
        # Amount far beyond the initial search bound; also an overflow regression:
        # q/b ends up ≈ 400, where the naive exp() would blow up.
        b = 25.0
        amount = 10_000.0
        shares = lmsr.calc_shares(amount, 0.0, 0.0, b, "YES")
        cost_diff = lmsr.lmsr_cost(shares, 0.0, b) - lmsr.lmsr_cost(0.0, 0.0, b)
        assert cost_diff == pytest.approx(amount, abs=1e-4)
        # Deep in the money the price ≈ $1/share, so shares ≈ amount (slightly above)
        assert amount < shares < amount + b

    def test_side_is_case_insensitive(self):
        a = lmsr.calc_shares(10.0, 40.0, 60.0, 100.0, "YES")
        b_ = lmsr.calc_shares(10.0, 40.0, 60.0, 100.0, "yes")
        assert a == pytest.approx(b_)

    def test_zero_cash_buys_no_shares(self):
        assert lmsr.calc_shares(0.0, 10.0, 10.0, 100.0, "YES") == pytest.approx(0.0, abs=1e-4)

    def test_round_trip_buy_then_sell(self):
        # Selling the shares just bought (via cost difference, as /sell does)
        # returns the same cash, minus nothing — LMSR is path-independent.
        q_yes, q_no, b, amount = 15.0, 45.0, 100.0, 30.0
        shares = lmsr.calc_shares(amount, q_yes, q_no, b, "YES")
        proceeds = lmsr.lmsr_cost(q_yes + shares, q_no, b) - lmsr.lmsr_cost(q_yes, q_no, b)
        assert proceeds == pytest.approx(amount, abs=1e-5)
