from __future__ import annotations

import math
import json
from datetime import date, datetime
from typing import Any, Iterable


def _date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    return datetime.fromisoformat(text.replace("Z", "+00:00")).date()


def _quote_price(row: dict[str, Any]) -> float | None:
    for key in ("settlement", "last"):
        if row.get(key) is not None:
            return float(row[key])
    if row.get("bid") is not None and row.get("ask") is not None:
        return (float(row["bid"]) + float(row["ask"])) / 2
    if row.get("bid") is not None:
        return float(row["bid"])
    if row.get("ask") is not None:
        return float(row["ask"])
    return None


def build_forward_curve(
    quotes: Iterable[dict[str, Any]],
    *,
    spot_price: float | None = None,
    valuation_date: str | date | datetime | None = None,
) -> list[dict[str, Any]]:
    today = _date(valuation_date or date.today())
    curve: list[dict[str, Any]] = []
    for quote in quotes:
        if str(quote.get("instrument_type", "")).lower() != "future":
            continue
        maturity_raw = str(quote.get("maturity_date", "")).strip()
        price = _quote_price(quote)
        if not maturity_raw or price is None:
            continue
        maturity = _date(maturity_raw)
        days = (maturity - today).days
        point: dict[str, Any] = {
            "symbol": quote.get("symbol", ""),
            "underlying": quote.get("underlying", ""),
            "maturity_date": maturity.isoformat(),
            "days_to_maturity": days,
            "future_price": price,
            "settlement": quote.get("settlement"),
            "last": quote.get("last"),
            "open_interest": quote.get("open_interest"),
            "volume": quote.get("volume"),
        }
        if spot_price is not None and spot_price > 0:
            point["basis"] = price - spot_price
            point["basis_pct"] = price / spot_price - 1
            point["annualized_curve_rate"] = (
                (price / spot_price) ** (365 / days) - 1 if days > 0 else None
            )
        curve.append(point)
    return sorted(curve, key=lambda row: (row["underlying"], row["maturity_date"]))


def normal_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


def black76_price(
    future_price: float,
    strike: float,
    time_years: float,
    risk_free_rate: float,
    volatility: float,
    option_type: str,
) -> float:
    if min(future_price, strike) <= 0 or time_years < 0 or volatility < 0:
        raise ValueError("Parámetros inválidos para Black-76")
    option = option_type.lower()
    if option not in {"call", "put", "c", "p"}:
        raise ValueError("option_type debe ser call o put")
    discount = math.exp(-risk_free_rate * time_years)
    if time_years == 0 or volatility == 0:
        intrinsic = max(future_price - strike, 0) if option in {"call", "c"} else max(strike - future_price, 0)
        return discount * intrinsic
    sigma_root_t = volatility * math.sqrt(time_years)
    d1 = (math.log(future_price / strike) + 0.5 * volatility**2 * time_years) / sigma_root_t
    d2 = d1 - sigma_root_t
    if option in {"call", "c"}:
        return discount * (future_price * normal_cdf(d1) - strike * normal_cdf(d2))
    return discount * (strike * normal_cdf(-d2) - future_price * normal_cdf(-d1))


def implied_volatility_black76(
    market_price: float,
    future_price: float,
    strike: float,
    time_years: float,
    risk_free_rate: float,
    option_type: str,
    *,
    tolerance: float = 1e-7,
    max_iterations: int = 200,
) -> float | None:
    if market_price < 0 or time_years <= 0:
        return None
    low, high = 1e-8, 5.0
    low_price = black76_price(future_price, strike, time_years, risk_free_rate, low, option_type)
    high_price = black76_price(future_price, strike, time_years, risk_free_rate, high, option_type)
    if market_price < low_price - tolerance or market_price > high_price + tolerance:
        return None
    for _ in range(max_iterations):
        middle = (low + high) / 2
        estimate = black76_price(future_price, strike, time_years, risk_free_rate, middle, option_type)
        if abs(estimate - market_price) <= tolerance:
            return middle
        if estimate < market_price:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def option_implied_volatility(
    option_quote: dict[str, Any],
    future_price: float,
    *,
    valuation_date: str | date | datetime | None = None,
    risk_free_rate: float = 0.0,
) -> float | None:
    metadata = option_quote.get("metadata")
    if metadata is None and option_quote.get("metadata_json"):
        try:
            metadata = json.loads(str(option_quote["metadata_json"]))
        except json.JSONDecodeError:
            metadata = {}
    if isinstance(metadata, dict) and metadata.get("maturity_date_precision") == "contract_month_end_proxy":
        return None
    premium = _quote_price(option_quote)
    strike = option_quote.get("strike")
    maturity_raw = str(option_quote.get("maturity_date", "")).strip()
    option_type = str(option_quote.get("option_type", "")).strip()
    if premium is None or strike is None or not maturity_raw or not option_type:
        return None
    today = _date(valuation_date or date.today())
    days = (_date(maturity_raw) - today).days
    if days <= 0:
        return None
    return implied_volatility_black76(
        market_price=premium,
        future_price=future_price,
        strike=float(strike),
        time_years=days / 365,
        risk_free_rate=risk_free_rate,
        option_type=option_type,
    )
