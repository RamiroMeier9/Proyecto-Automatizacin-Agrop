import unittest

from inta_forrajes.economics import (
    break_even_yield_dm,
    equivalent_annual_cost,
    evaluate_alternative,
    net_present_value,
    present_value,
)
from inta_forrajes.models import Alternative, RecipeItem


class EconomicsTests(unittest.TestCase):
    def test_present_value_and_equivalent_annual_cost(self):
        pv = present_value({0: 1000, 1: 110}, 0.10)
        self.assertAlmostEqual(pv, 1100.0, places=8)
        eac = equivalent_annual_cost(pv, 0.10, 2)
        self.assertAlmostEqual(eac, 633.8095238095, places=6)

    def test_zero_rate(self):
        self.assertEqual(equivalent_annual_cost(1000, 0, 5), 200)

    def test_npv(self):
        self.assertAlmostEqual(net_present_value(100, [60, 60], 0.10), 4.1322314, places=6)

    def test_complete_alternative(self):
        alternative = Alternative(
            alternative_id="demo",
            name="Demo",
            useful_life_years=2,
            yield_dm_kg_ha=4000,
            utilization_rate=0.75,
            conversion_kg_dm_per_kg_meat=8,
        )
        recipe = [
            RecipeItem("demo", 0, "semilla", "Semilla", 10, "kg", "SEED", None, "ARS"),
            RecipeItem("demo", 1, "mantenimiento", "Mantenimiento", 1, "ha", "MAINT", None, "ARS"),
        ]
        prices = [
            {"series_id": "SEED", "observed_at": "2026-01-01", "value": 100, "currency": "ARS"},
            {"series_id": "MAINT", "observed_at": "2026-01-01", "value": 110, "currency": "ARS"},
        ]
        result = evaluate_alternative(alternative, recipe, prices, 0.10)
        self.assertTrue(result.cost_complete)
        self.assertFalse(result.missing_inputs)
        self.assertAlmostEqual(result.present_value_cost_ha, 1100)
        self.assertAlmostEqual(result.cost_per_kg_produced_dm, result.equivalent_annual_cost_ha / 4000)
        self.assertAlmostEqual(result.annual_usable_dm_kg_ha, 3000)
        self.assertAlmostEqual(result.cost_per_kg_meat_equivalent, result.cost_per_kg_usable_dm * 8)

    def test_missing_inputs_are_not_replaced_by_zero(self):
        alternative = Alternative("demo", "Demo", 1, None, None, None)
        recipe = [RecipeItem("demo", 0, "semilla", "Semilla", None, "kg", "SEED")]
        result = evaluate_alternative(alternative, recipe, [], 0.10)
        self.assertFalse(result.cost_complete)
        self.assertIn("cantidad: Semilla", result.missing_inputs)
        self.assertIn("rendimiento anual de materia seca", result.missing_inputs)

    def test_break_even_yield(self):
        value = break_even_yield_dm(120000, 2400, 0.5, 10)
        self.assertEqual(value, 1000)


if __name__ == "__main__":
    unittest.main()
