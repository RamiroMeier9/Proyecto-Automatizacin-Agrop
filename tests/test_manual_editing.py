import tempfile
import unittest
from pathlib import Path

from inta_forrajes.csv_io import read_alternatives, read_rows, write_alternatives, write_manual_prices
from inta_forrajes.models import Alternative, PriceObservation


class ManualEditingTests(unittest.TestCase):
    def test_price_writer_updates_catalog_and_preserves_pending_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual_prices.csv"
            path.write_text(
                "observed_at,series_id,item,value,currency,unit,source,source_url,notes\n"
                ",SEMILLA_AVENA,Semilla de avena,,ARS,kg,manual,,Pendiente\n"
                ",LABOR,Siembra,,ARS,ha,manual,,Pendiente\n",
                encoding="utf-8",
            )
            write_manual_prices(
                path,
                [
                    PriceObservation(
                        observed_at="2026-11-27",
                        series_id="SEMILLA_AVENA",
                        item="Semilla de avena",
                        value=1234.5,
                        currency="ARS",
                        unit="kg",
                        source="manual",
                        ingestion_method="formulario",
                        metadata={"notes": "Presupuesto local"},
                    )
                ],
            )
            rows = read_rows(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["value"], "1234.5")
            self.assertEqual(rows[1]["series_id"], "LABOR")

    def test_alternative_writer_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "alternatives.csv"
            item = Alternative(
                alternative_id="avena",
                name="Avena",
                useful_life_years=1,
                yield_dm_kg_ha=5000,
                utilization_rate=0.7,
                conversion_kg_dm_per_kg_meat=8,
                soil_position="loma",
                establishment_system="directa",
                yield_low_dm_kg_ha=3000,
                yield_high_dm_kg_ha=7000,
            )
            write_alternatives(path, [item])
            restored = read_alternatives(path)
            self.assertEqual(restored, [item])


if __name__ == "__main__":
    unittest.main()
