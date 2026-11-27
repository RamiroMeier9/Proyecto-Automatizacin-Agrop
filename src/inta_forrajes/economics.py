from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .models import Alternative, EvaluationResult, RecipeItem


def present_value(cash_flows: dict[int, float], annual_rate: float) -> float:
    if annual_rate <= -1:
        raise ValueError("La tasa debe ser mayor que -100 %")
    return sum(value / ((1 + annual_rate) ** year) for year, value in cash_flows.items())


def equivalent_annual_cost(present_value_cost: float, annual_rate: float, years: int) -> float:
    if years <= 0:
        raise ValueError("La vida útil debe ser positiva")
    if annual_rate == 0:
        return present_value_cost / years
    factor = annual_rate * (1 + annual_rate) ** years / ((1 + annual_rate) ** years - 1)
    return present_value_cost * factor


def net_present_value(initial_investment: float, net_flows: Iterable[float], annual_rate: float) -> float:
    return -initial_investment + sum(
        flow / ((1 + annual_rate) ** year) for year, flow in enumerate(net_flows, start=1)
    )


def latest_price_map(price_rows: Iterable[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in price_rows:
        series_id = str(row.get("series_id", ""))
        if not series_id:
            continue
        current = latest.get(series_id)
        if current is None or str(row.get("observed_at", "")) >= str(current.get("observed_at", "")):
            latest[series_id] = row
    return latest


def _converted_price(
    price_row: dict,
    target_currency: str,
    prices: dict[str, dict],
) -> float | None:
    value = price_row.get("value")
    if value is None:
        return None
    value = float(value)
    source_currency = str(price_row.get("currency", target_currency)).upper()
    target_currency = target_currency.upper()
    if source_currency == target_currency:
        return value
    if {source_currency, target_currency} == {"USD", "ARS"}:
        fx = prices.get("FX_BCRA_USD_ARS")
        if not fx or fx.get("value") is None:
            return None
        exchange_rate = float(fx["value"])
        return value * exchange_rate if source_currency == "USD" else value / exchange_rate
    return None


def evaluate_alternative(
    alternative: Alternative,
    recipe: Iterable[RecipeItem],
    price_rows: Iterable[dict],
    annual_rate: float,
) -> EvaluationResult:
    prices = latest_price_map(price_rows)
    missing: list[str] = []
    cost_complete = True
    costs_by_year: dict[int, float] = defaultdict(float)

    for component in recipe:
        if component.alternative_id != alternative.alternative_id:
            continue
        if component.quantity is None:
            missing.append(f"cantidad: {component.item}")
            cost_complete = False
            continue
        unit_price = component.manual_unit_price
        if unit_price is None and component.price_series_id:
            row = prices.get(component.price_series_id)
            unit_price = _converted_price(row, component.currency, prices) if row else None
        if unit_price is None:
            missing.append(f"precio: {component.item}")
            cost_complete = False
            continue
        costs_by_year[component.year] += component.quantity * unit_price

    life = alternative.useful_life_years
    pv_cost = present_value(dict(costs_by_year), annual_rate)
    eac = equivalent_annual_cost(pv_cost, annual_rate, life)

    annual_produced_dm = alternative.yield_dm_kg_ha
    cost_per_produced_dm: float | None = None
    annual_usable_dm: float | None = None
    cost_per_dm: float | None = None
    cost_per_meat: float | None = None
    if alternative.yield_dm_kg_ha is None:
        missing.append("rendimiento anual de materia seca")
    elif alternative.yield_dm_kg_ha > 0 and cost_complete:
        cost_per_produced_dm = eac / alternative.yield_dm_kg_ha
    if alternative.utilization_rate is None:
        missing.append("porcentaje de aprovechamiento")
    if alternative.yield_dm_kg_ha is not None and alternative.utilization_rate is not None:
        annual_usable_dm = alternative.yield_dm_kg_ha * alternative.utilization_rate
        if annual_usable_dm > 0 and cost_complete:
            cost_per_dm = eac / annual_usable_dm
    if alternative.conversion_kg_dm_per_kg_meat is None:
        missing.append("conversión kg MS/kg carne")
    elif cost_per_dm is not None:
        cost_per_meat = cost_per_dm * alternative.conversion_kg_dm_per_kg_meat

    return EvaluationResult(
        alternative_id=alternative.alternative_id,
        cost_complete=cost_complete,
        present_value_cost_ha=pv_cost,
        equivalent_annual_cost_ha=eac,
        annual_produced_dm_kg_ha=annual_produced_dm,
        cost_per_kg_produced_dm=cost_per_produced_dm,
        annual_usable_dm_kg_ha=annual_usable_dm,
        cost_per_kg_usable_dm=cost_per_dm,
        cost_per_kg_meat_equivalent=cost_per_meat,
        missing_inputs=tuple(dict.fromkeys(missing)),
        cash_costs_by_year=dict(sorted(costs_by_year.items())),
    )


def break_even_yield_dm(
    equivalent_annual_cost_ha: float,
    output_price_per_kg_meat: float,
    utilization_rate: float,
    conversion_kg_dm_per_kg_meat: float,
) -> float:
    if min(output_price_per_kg_meat, utilization_rate, conversion_kg_dm_per_kg_meat) <= 0:
        raise ValueError("Precio, aprovechamiento y conversión deben ser positivos")
    required_meat_kg = equivalent_annual_cost_ha / output_price_per_kg_meat
    return required_meat_kg * conversion_kg_dm_per_kg_meat / utilization_rate
