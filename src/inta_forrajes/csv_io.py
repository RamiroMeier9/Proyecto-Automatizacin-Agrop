from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Sequence

from .connectors.utils import as_float
from .models import A3Quote, Alternative, PriceObservation, RecipeItem


def read_rows(path: str | Path) -> list[dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def read_manual_prices(path: str | Path) -> tuple[list[PriceObservation], list[str]]:
    observations: list[PriceObservation] = []
    skipped: list[str] = []
    for index, row in enumerate(read_rows(path), start=2):
        value = as_float(row.get("value"))
        observed_at = str(row.get("observed_at", "")).strip()
        series_id = str(row.get("series_id", "")).strip()
        if value is None or not observed_at or not series_id:
            skipped.append(f"fila {index}: faltan fecha, serie o valor")
            continue
        observations.append(
            PriceObservation(
                observed_at=observed_at,
                series_id=series_id,
                item=str(row.get("item", series_id)).strip(),
                value=value,
                currency=str(row.get("currency", "ARS")).strip().upper(),
                unit=str(row.get("unit", "")).strip(),
                source=str(row.get("source", "manual")).strip() or "manual",
                source_url=str(row.get("source_url", "")).strip(),
                ingestion_method="csv",
                metadata={"notes": row.get("notes", "")},
            )
        )
    return observations, skipped


def write_manual_prices(
    path: str | Path,
    observations: Sequence[PriceObservation],
) -> None:
    """Actualiza el catálogo manual sin perder las filas todavía incompletas."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "observed_at",
        "series_id",
        "item",
        "value",
        "currency",
        "unit",
        "source",
        "source_url",
        "notes",
    ]
    existing = read_rows(output_path)
    positions = {
        str(row.get("series_id", "")).strip(): index
        for index, row in enumerate(existing)
        if str(row.get("series_id", "")).strip()
    }
    for observation in observations:
        row = {
            "observed_at": observation.observed_at,
            "series_id": observation.series_id,
            "item": observation.item,
            "value": observation.value,
            "currency": observation.currency,
            "unit": observation.unit,
            "source": observation.source or "manual",
            "source_url": observation.source_url,
            "notes": str(observation.metadata.get("notes", "")),
        }
        if observation.series_id in positions:
            existing[positions[observation.series_id]] = row
        else:
            positions[observation.series_id] = len(existing)
            existing.append(row)

    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in existing:
            writer.writerow({column: row.get(column, "") for column in columns})
    os.replace(temporary, output_path)


def read_a3_quotes(path: str | Path) -> tuple[list[A3Quote], list[str]]:
    quotes: list[A3Quote] = []
    skipped: list[str] = []
    for index, row in enumerate(read_rows(path), start=2):
        symbol = str(row.get("symbol", "")).strip()
        as_of = str(row.get("as_of", "")).strip()
        values = [as_float(row.get(key)) for key in ("bid", "ask", "last", "settlement")]
        if not symbol or not as_of or all(value is None for value in values):
            skipped.append(f"fila {index}: falta símbolo, fecha o un precio")
            continue
        quotes.append(
            A3Quote(
                as_of=as_of,
                symbol=symbol,
                market_id=str(row.get("market_id", "ROFX")).strip() or "ROFX",
                instrument_type=str(row.get("instrument_type", "unknown")).strip().lower(),
                underlying=str(row.get("underlying", "")).strip(),
                maturity_date=str(row.get("maturity_date", "")).strip(),
                strike=as_float(row.get("strike")),
                option_type=str(row.get("option_type", "")).strip().lower(),
                currency=str(row.get("currency", "")).strip().upper(),
                unit=str(row.get("unit", "")).strip(),
                bid=values[0],
                ask=values[1],
                last=values[2],
                settlement=values[3],
                open_interest=as_float(row.get("open_interest")),
                volume=as_float(row.get("volume")),
                source_url=str(row.get("source_url", "")).strip(),
                ingestion_method="csv",
                metadata={"notes": row.get("notes", "")},
            )
        )
    return quotes, skipped


def read_alternatives(path: str | Path) -> list[Alternative]:
    alternatives: list[Alternative] = []
    for row in read_rows(path):
        identifier = str(row.get("alternative_id", "")).strip()
        if not identifier:
            continue
        alternatives.append(
            Alternative(
                alternative_id=identifier,
                name=str(row.get("name", identifier)).strip(),
                useful_life_years=int(as_float(row.get("useful_life_years")) or 1),
                yield_dm_kg_ha=as_float(row.get("yield_dm_kg_ha")),
                utilization_rate=as_float(row.get("utilization_rate")),
                conversion_kg_dm_per_kg_meat=as_float(row.get("conversion_kg_dm_per_kg_meat")),
                soil_position=str(row.get("soil_position", "")).strip(),
                establishment_system=str(row.get("establishment_system", "")).strip(),
                source_reference=str(row.get("source_reference", "")).strip(),
                validation_status=str(row.get("validation_status", "pending")).strip(),
                notes=str(row.get("notes", "")).strip(),
                yield_low_dm_kg_ha=as_float(row.get("yield_low_dm_kg_ha")),
                yield_high_dm_kg_ha=as_float(row.get("yield_high_dm_kg_ha")),
            )
        )
    return alternatives


def write_alternatives(path: str | Path, alternatives: Sequence[Alternative]) -> None:
    """Guarda los supuestos productivos editables con un esquema estable."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "alternative_id",
        "name",
        "soil_position",
        "establishment_system",
        "useful_life_years",
        "yield_dm_kg_ha",
        "yield_low_dm_kg_ha",
        "yield_high_dm_kg_ha",
        "utilization_rate",
        "conversion_kg_dm_per_kg_meat",
        "source_reference",
        "validation_status",
        "notes",
    ]
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item in alternatives:
            writer.writerow(
                {
                    "alternative_id": item.alternative_id,
                    "name": item.name,
                    "soil_position": item.soil_position,
                    "establishment_system": item.establishment_system,
                    "useful_life_years": item.useful_life_years,
                    "yield_dm_kg_ha": item.yield_dm_kg_ha,
                    "yield_low_dm_kg_ha": item.yield_low_dm_kg_ha,
                    "yield_high_dm_kg_ha": item.yield_high_dm_kg_ha,
                    "utilization_rate": item.utilization_rate,
                    "conversion_kg_dm_per_kg_meat": item.conversion_kg_dm_per_kg_meat,
                    "source_reference": item.source_reference,
                    "validation_status": item.validation_status,
                    "notes": item.notes,
                }
            )
    os.replace(temporary, output_path)


def read_recipes(path: str | Path) -> list[RecipeItem]:
    recipes: list[RecipeItem] = []
    for row in read_rows(path):
        identifier = str(row.get("alternative_id", "")).strip()
        item = str(row.get("item", "")).strip()
        if not identifier or not item:
            continue
        recipes.append(
            RecipeItem(
                alternative_id=identifier,
                year=int(as_float(row.get("year")) or 0),
                category=str(row.get("category", "otro")).strip(),
                item=item,
                quantity=as_float(row.get("quantity")),
                unit=str(row.get("unit", "")).strip(),
                price_series_id=str(row.get("price_series_id", "")).strip(),
                manual_unit_price=as_float(row.get("manual_unit_price")),
                currency=str(row.get("currency", "ARS")).strip().upper(),
                notes=str(row.get("notes", "")).strip(),
            )
        )
    return recipes


def read_watchlist(path: str | Path) -> list[dict[str, Any]]:
    return [row for row in read_rows(path) if str(row.get("symbol", "")).strip()]


def write_instruments(path: str | Path, instruments: list[dict[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "symbol",
        "market_id",
        "segment",
        "cficode",
        "instrument_type",
        "description",
        "maturity_date",
        "currency",
        "contract_multiplier",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item in instruments:
            instrument_id = item.get("instrumentId") or {}
            segment = item.get("segment") or {}
            cfi = str(item.get("cficode", ""))
            writer.writerow(
                {
                    "symbol": instrument_id.get("symbol") or item.get("symbol") or "",
                    "market_id": instrument_id.get("marketId") or segment.get("marketId") or "",
                    "segment": segment.get("marketSegmentId") or "",
                    "cficode": cfi,
                    "instrument_type": "future" if cfi.startswith("F") else "option" if cfi.startswith("O") else "unknown",
                    "description": item.get("securityDescription") or "",
                    "maturity_date": item.get("maturityDate") or "",
                    "currency": item.get("currency") or "",
                    "contract_multiplier": item.get("contractMultiplier") or "",
                }
            )
