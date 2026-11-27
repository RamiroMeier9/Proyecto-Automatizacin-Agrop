import tempfile
import unittest
from pathlib import Path

from inta_forrajes.models import A3Quote, PriceObservation
from inta_forrajes.storage import Storage


class StorageTests(unittest.TestCase):
    def test_upsert_and_latest(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory) / "test.sqlite3")
            storage.initialize()
            storage.upsert_prices(
                [
                    PriceObservation("2026-01-01", "SERIE", "Item", 10, "ARS", "kg", "manual"),
                    PriceObservation("2026-02-01", "SERIE", "Item", 12, "ARS", "kg", "manual"),
                ]
            )
            self.assertEqual(storage.latest_prices()[0]["value"], 12)
            storage.upsert_a3_quotes([A3Quote("2026-01-01", "DEMO", settlement=100)])
            self.assertEqual(storage.latest_a3_quotes()[0]["settlement"], 100)


if __name__ == "__main__":
    unittest.main()
