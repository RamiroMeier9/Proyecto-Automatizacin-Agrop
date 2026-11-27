import json
import unittest

from inta_forrajes.pipeline import build_public_snapshot


class PublicSnapshotTests(unittest.TestCase):
    def test_excludes_private_and_manual_sources(self):
        prices = [
            {
                "observed_at": "2026-11-26",
                "series_id": "FX_BCRA_USD_ARS",
                "item": "Dólar",
                "value": 1600,
                "currency": "ARS",
                "unit": "ARS/USD",
                "source": "bcra",
                "source_url": "https://www.bcra.gob.ar/",
                "ingestion_method": "api",
                "metadata_json": json.dumps({"public": True}),
            },
            {
                "observed_at": "2026-11-26",
                "series_id": "PRIVATE",
                "item": "Privado",
                "value": 1,
                "currency": "ARS",
                "unit": "kg",
                "source": "sio_granos",
                "source_url": "",
                "ingestion_method": "api",
                "metadata_json": "{}",
            },
        ]
        base_quote = {
            "as_of": "2026-11-26",
            "symbol": "MAI.ROS/ABR27",
            "market_id": "A3",
            "instrument_type": "future",
            "underlying": "MAI.ROS",
            "maturity_date": "2027-04-30",
            "strike": None,
            "option_type": "",
            "currency": "USD",
            "unit": "USD/t",
            "bid": None,
            "ask": None,
            "last": 180,
            "settlement": 180,
            "open_interest": 10,
            "volume": 5,
            "ingestion_method": "api",
            "metadata_json": "{}",
        }
        quotes = [
            {**base_quote, "source_url": "https://marketdata.mae.com.ar/"},
            {**base_quote, "symbol": "PRIVATE", "source_url": "https://api.remarkets.primary.com.ar/"},
        ]

        snapshot = build_public_snapshot(prices, quotes)

        self.assertEqual([row["series_id"] for row in snapshot["prices"]], ["FX_BCRA_USD_ARS"])
        self.assertEqual([row["symbol"] for row in snapshot["a3_quotes"]], ["MAI.ROS/ABR27"])
        self.assertNotIn("metadata_json", snapshot["prices"][0])


if __name__ == "__main__":
    unittest.main()
