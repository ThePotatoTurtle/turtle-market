# test_graphs.py
# Tests for graph generation logic in graphs.py: odds-history reconstruction
# and y-axis auto-scaling. Rendering gets a smoke test.
# Run with: pytest test_graphs.py

import datetime
import os

import pytest

import graphs
import lmsr

UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def iso(dt: datetime.datetime) -> str:
    return dt.isoformat()


def make_market(b=100.0, created=T0, resolved=False, resolution=None, resolution_date=None):
    return {
        'question': 'Test question?',
        'b': b,
        'created_at': iso(created),
        'resolved': resolved,
        'resolution': resolution,
        'resolution_date': iso(resolution_date) if resolution_date else None,
    }


class TestYBounds:
    def test_flat_fifty(self):
        # 50 is a multiple of 5: strictly below/above → 45..55
        assert graphs.y_bounds([0.5]) == (45.0, 55.0)

    def test_rounds_to_next_increment(self):
        assert graphs.y_bounds([0.32, 0.61]) == (30.0, 65.0)

    def test_exact_multiples_get_padding(self):
        # Bounds must be strictly below/above the extremes
        assert graphs.y_bounds([0.40, 0.60]) == (35.0, 65.0)

    def test_clamped_to_0_100(self):
        lo, hi = graphs.y_bounds([0.98, 1.0])
        assert hi == 100.0
        lo, hi = graphs.y_bounds([0.0, 0.02])
        assert lo == 0.0


class TestOddsHistory:
    def test_no_trades_active_market(self):
        now = T0 + datetime.timedelta(days=3)
        points, res = graphs.odds_history(make_market(), [], now=now)
        assert res is None
        assert points == [(T0, 0.5), (now, 0.5)]

    def test_replay_matches_lmsr(self):
        b = 100.0
        trades = [
            ('YES', 30.0, iso(T0 + datetime.timedelta(days=1))),
            ('NO', 50.0, iso(T0 + datetime.timedelta(days=2))),
            ('YES', -10.0, iso(T0 + datetime.timedelta(days=3))),  # a sell
        ]
        now = T0 + datetime.timedelta(days=5)
        points, res = graphs.odds_history(make_market(b=b), trades, now=now)
        assert res is None
        # creation + one per trade + terminal flat point
        assert len(points) == 5
        assert points[0] == (T0, 0.5)
        assert points[1][1] == pytest.approx(lmsr.lmsr_price(30, 0, b))
        assert points[2][1] == pytest.approx(lmsr.lmsr_price(30, 50, b))
        assert points[3][1] == pytest.approx(lmsr.lmsr_price(20, 50, b))
        # Flat tail: odds hold their last value until now
        assert points[4] == (now, points[3][1])

    @pytest.mark.parametrize("resolution,expected", [
        ('YES', 1.0), ('NO', 0.0), ('HALF', 0.5),
    ])
    def test_resolved_market_final_point(self, resolution, expected):
        res_date = T0 + datetime.timedelta(days=10)
        market = make_market(resolved=True, resolution=resolution, resolution_date=res_date)
        trades = [('YES', 20.0, iso(T0 + datetime.timedelta(days=1)))]
        points, res = graphs.odds_history(market, trades)
        # Line ends flat at the resolution date; settled odds are a separate point
        assert points[-1][0] == res_date
        assert points[-1][1] == points[-2][1]
        assert res == (res_date, expected)

    def test_duplicate_timestamps_keep_last(self):
        # Backfilled created_at can equal the first trade's timestamp;
        # the 50% creation point must not linger at the same instant.
        trades = [('YES', 30.0, iso(T0))]
        now = T0 + datetime.timedelta(days=1)
        points, _ = graphs.odds_history(make_market(), trades, now=now)
        assert len(points) == 2
        assert points[0][0] == T0
        assert points[0][1] == pytest.approx(lmsr.lmsr_price(30, 0, 100.0))

    def test_timestamps_strictly_increasing(self):
        trades = [
            ('YES', 10.0, iso(T0 + datetime.timedelta(hours=1))),
            ('NO', 5.0, iso(T0 + datetime.timedelta(hours=1))),  # same second
            ('YES', 2.0, iso(T0 + datetime.timedelta(hours=2))),
        ]
        points, _ = graphs.odds_history(make_market(), trades, now=T0 + datetime.timedelta(days=1))
        times = [t for t, _ in points]
        assert all(a < z for a, z in zip(times, times[1:]))


class TestRender:
    def test_renders_png(self, tmp_path):
        market = make_market()
        trades = [
            ('YES', 30.0, iso(T0 + datetime.timedelta(days=1))),
            ('NO', 45.0, iso(T0 + datetime.timedelta(days=2, hours=6))),
            ('YES', 12.0, iso(T0 + datetime.timedelta(days=4))),
        ]
        path = graphs.render_market_graph('testmkt', market, trades, out_dir=str(tmp_path))
        assert os.path.exists(path)
        assert path.endswith('.png')
        with open(path, 'rb') as f:
            assert f.read(8) == b'\x89PNG\r\n\x1a\n'

    def test_renders_resolved_market(self, tmp_path):
        market = make_market(resolved=True, resolution='YES',
                             resolution_date=T0 + datetime.timedelta(days=7))
        trades = [('YES', 60.0, iso(T0 + datetime.timedelta(days=1)))]
        path = graphs.render_market_graph('resolved1', market, trades, out_dir=str(tmp_path))
        assert os.path.exists(path)
