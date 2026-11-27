import unittest

from inta_forrajes.forward_curve import (
    black76_price,
    build_forward_curve,
    implied_volatility_black76,
)


class ForwardCurveTests(unittest.TestCase):
    def test_curve_and_basis(self):
        quotes = [
            {
                "symbol": "DEMO/ENE27",
                "underlying": "DEMO",
                "instrument_type": "future",
                "maturity_date": "2027-01-31",
                "settlement": 110,
                "last": 109,
            }
        ]
        curve = build_forward_curve(quotes, spot_price=100, valuation_date="2026-11-27")
        self.assertEqual(len(curve), 1)
        self.assertEqual(curve[0]["basis"], 10)
        self.assertAlmostEqual(curve[0]["basis_pct"], 0.10)

    def test_black76_implied_volatility_round_trip(self):
        premium = black76_price(100, 100, 0.5, 0.05, 0.30, "call")
        implied = implied_volatility_black76(premium, 100, 100, 0.5, 0.05, "call")
        self.assertIsNotNone(implied)
        self.assertAlmostEqual(implied, 0.30, places=5)

    def test_invalid_option_type(self):
        with self.assertRaises(ValueError):
            black76_price(100, 100, 1, 0.05, 0.2, "otro")


if __name__ == "__main__":
    unittest.main()
