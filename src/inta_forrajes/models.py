from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PriceObservation:
    observed_at: str
    series_id: str
    item: str
    value: float
    currency: str
    unit: str
    source: str
    source_url: str = ""
    ingestion_method: str = "api"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class A3Quote:
    as_of: str
    symbol: str
    market_id: str = "ROFX"
    instrument_type: str = "unknown"
    underlying: str = ""
    maturity_date: str = ""
    strike: float | None = None
    option_type: str = ""
    currency: str = ""
    unit: str = ""
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    settlement: float | None = None
    open_interest: float | None = None
    volume: float | None = None
    source_url: str = ""
    ingestion_method: str = "api"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def reference_price(self) -> float | None:
        """Prioriza ajuste, último y punto medio, en ese orden."""
        if self.settlement is not None:
            return self.settlement
        if self.last is not None:
            return self.last
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return self.bid if self.bid is not None else self.ask


@dataclass(frozen=True)
class Alternative:
    alternative_id: str
    name: str
    useful_life_years: int
    yield_dm_kg_ha: float | None
    utilization_rate: float | None
    conversion_kg_dm_per_kg_meat: float | None
    soil_position: str = ""
    establishment_system: str = ""
    source_reference: str = ""
    validation_status: str = "pending"
    notes: str = ""
    yield_low_dm_kg_ha: float | None = None
    yield_high_dm_kg_ha: float | None = None


@dataclass(frozen=True)
class RecipeItem:
    alternative_id: str
    year: int
    category: str
    item: str
    quantity: float | None
    unit: str
    price_series_id: str = ""
    manual_unit_price: float | None = None
    currency: str = "ARS"
    notes: str = ""


@dataclass(frozen=True)
class EvaluationResult:
    alternative_id: str
    cost_complete: bool
    present_value_cost_ha: float
    equivalent_annual_cost_ha: float
    annual_produced_dm_kg_ha: float | None
    cost_per_kg_produced_dm: float | None
    annual_usable_dm_kg_ha: float | None
    cost_per_kg_usable_dm: float | None
    cost_per_kg_meat_equivalent: float | None
    missing_inputs: tuple[str, ...]
    cash_costs_by_year: dict[int, float]
    evaluated_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
