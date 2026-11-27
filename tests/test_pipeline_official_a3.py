import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from inta_forrajes.pipeline import Pipeline


class FakeOfficialConnector:
    calls = []

    def __init__(self, api_key, environment="uat"):
        self.calls.append((api_key, environment))

    def fetch_final_report(self, report_date):
        return [{"fecha": report_date.isoformat(), "resultado": "ok"}]


class OfficialA3PipelineTests(unittest.TestCase):
    def test_key_is_used_and_response_stays_in_private_snapshot(self):
        FakeOfficialConnector.calls.clear()
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {"A3_MD_API_KEY": "test-secret", "A3_MD_ENV": "uat"},
                clear=False,
            ), patch(
                "inta_forrajes.pipeline.A3OfficialAPIKeyConnector",
                FakeOfficialConnector,
            ):
                pipeline = Pipeline(Path(directory))
                result = pipeline._update_a3_official_report()

            self.assertEqual(result["status"], "ok")
            self.assertEqual(FakeOfficialConnector.calls, [("test-secret", "uat")])
            self.assertTrue(pipeline.paths.official_a3_snapshot.exists())
            saved = json.loads(
                pipeline.paths.official_a3_snapshot.read_text(encoding="utf-8")
            )
            self.assertEqual(saved["environment"], "uat")
            self.assertEqual(saved["data"][0]["resultado"], "ok")
            self.assertNotIn("test-secret", json.dumps(saved))

    def test_missing_key_is_reported_without_creating_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True):
                pipeline = Pipeline(Path(directory))
                result = pipeline._update_a3_official_report()

            self.assertEqual(result["status"], "skipped")
            self.assertFalse(pipeline.paths.official_a3_snapshot.exists())

    def test_public_snapshot_is_loaded_into_local_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public_file = root / "data" / "public" / "latest.json"
            public_file.parent.mkdir(parents=True)
            public_file.write_text(
                json.dumps(
                    {
                        "prices": [
                            {
                                "observed_at": "2026-11-27",
                                "series_id": "FX_BCRA_USD_ARS",
                                "item": "Dólar",
                                "value": 1500,
                                "currency": "ARS",
                                "unit": "ARS/USD",
                                "source": "bcra",
                                "source_url": "https://www.bcra.gob.ar/",
                                "metadata": {},
                            }
                        ],
                        "a3_quotes": [
                            {
                                "as_of": "2026-11-27",
                                "symbol": "MAI.ROS/ABR27",
                                "market_id": "A3",
                                "instrument_type": "future",
                                "underlying": "MAI.ROS",
                                "maturity_date": "2027-04-30",
                                "settlement": 180,
                                "source_url": "https://marketdata.mae.com.ar/",
                                "metadata": {},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            pipeline = Pipeline(root)
            result = pipeline.import_public_snapshot()
            self.assertEqual(result["prices"], 1)
            self.assertEqual(result["a3_quotes"], 1)
            self.assertEqual(pipeline.storage.latest_prices()[0]["value"], 1500)
            self.assertEqual(pipeline.storage.latest_a3_quotes()[0]["symbol"], "MAI.ROS/ABR27")


if __name__ == "__main__":
    unittest.main()
