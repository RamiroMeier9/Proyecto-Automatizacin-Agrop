from __future__ import annotations

import calendar
import json
import re
from datetime import date, timedelta
from typing import Any

from .utils import as_float
from ..http import HTTPClient
from ..models import A3Quote


MONTHS = {
    "ENE": 1,
    "FEB": 2,
    "MAR": 3,
    "ABR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DIC": 12,
}


def contract_month_proxy(symbol: str) -> str:
    """Devuelve el fin del mes contractual, no el vencimiento legal exacto."""
    match = re.search(r"/(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)(\d{2})", symbol.upper())
    if not match:
        return ""
    month = MONTHS[match.group(1)]
    year = 2000 + int(match.group(2))
    return date(year, month, calendar.monthrange(year, month)[1]).isoformat()


def option_underlying(symbol: str) -> str:
    return symbol.split(" ", 1)[0].strip()


def product_code(symbol: str) -> str:
    return option_underlying(symbol).split("/", 1)[0].strip()


class A3AgroMarketDataConnector:
    """Precios agropecuarios de cierre publicados por el visor de A3."""

    base_url = "https://api.marketdata.mae.com.ar/api/cem/agropecuario"

    def __init__(self, client: HTTPClient | None = None) -> None:
        self.client = client or HTTPClient(timeout=45)

    def _fetch(self, instrument: str, date_from: date, date_to: date) -> list[dict[str, Any]]:
        filters = {
            "fechaDesde": date_from.isoformat(),
            "fechaHasta": date_to.isoformat(),
            "contratosSinVolumen": False,
        }
        response = self.client.request_json(
            "GET",
            f"{self.base_url}/{instrument}",
            params={"oData": json.dumps(filters, separators=(",", ":"))},
        )
        if not isinstance(response.data, list):
            raise RuntimeError(f"Respuesta inesperada de A3: {response.data}")
        return response.data

    @staticmethod
    def _common(row: dict[str, Any]) -> dict[str, Any]:
        symbol = str(row.get("posicion", "")).strip()
        return {
            "as_of": str(row.get("fecha", "")),
            "symbol": symbol,
            "market_id": "A3",
            "underlying": product_code(symbol),
            "maturity_date": contract_month_proxy(symbol),
            "currency": "USD" if ".ROS" in symbol.upper() else "",
            "unit": "USD/t" if ".ROS" in symbol.upper() else "",
            "last": as_float(row.get("precioUltimo")),
            "settlement": as_float(row.get("precioAjuste")),
            "open_interest": as_float(row.get("interesAbierto")),
            "volume": as_float(row.get("volumen")),
            "source_url": "https://marketdata.mae.com.ar/",
            "ingestion_method": "api",
            "metadata": {
                "open": row.get("precioApertura"),
                "low": row.get("precioMinimo"),
                "high": row.get("precioMaximo"),
                "variation_pct": row.get("variacionPorcentaje"),
                "trades": row.get("contratos"),
                "previous_settlement": row.get("ajusteAnterior"),
                "maturity_date_precision": "contract_month_end_proxy",
            },
        }

    def parse_futures(self, rows: list[dict[str, Any]]) -> list[A3Quote]:
        quotes: list[A3Quote] = []
        for row in rows:
            common = self._common(row)
            if not common["symbol"]:
                continue
            quotes.append(A3Quote(instrument_type="future", **common))
        return quotes

    def parse_options(self, rows: list[dict[str, Any]]) -> list[A3Quote]:
        quotes: list[A3Quote] = []
        for row in rows:
            common = self._common(row)
            symbol = str(common["symbol"])
            if not symbol:
                continue
            option_type_raw = str(row.get("tipo", "")).strip().lower()
            option_type = "call" if option_type_raw.startswith("call") else "put" if option_type_raw.startswith("put") else ""
            common["underlying"] = option_underlying(symbol)
            quotes.append(
                A3Quote(
                    instrument_type="option",
                    strike=as_float(row.get("ejercicio")),
                    option_type=option_type,
                    **common,
                )
            )
        return quotes

    def fetch_recent_quotes(self, days: int = 10) -> list[A3Quote]:
        end = date.today()
        start = end - timedelta(days=days)
        futures = self.parse_futures(self._fetch("fut", start, end))
        options = self.parse_options(self._fetch("opt", start, end))
        return futures + options


class A3OfficialAPIKeyConnector:
    """Cliente mínimo para la API formal que A3 habilita mediante x-api-key."""

    environments = {
        "production": "https://api.mae.com.ar/MarketData/v1",
        "uat": "https://apiuat.mae.com.ar/MarketData/v1",
    }

    def __init__(self, api_key: str, environment: str = "uat", client: HTTPClient | None = None) -> None:
        if not api_key:
            raise ValueError("Se requiere una API-Key de A3")
        if environment not in self.environments:
            raise ValueError("environment debe ser 'uat' o 'production'")
        self.api_key = api_key
        self.base_url = self.environments[environment]
        self.client = client or HTTPClient(timeout=45)

    def fetch_final_report(self, report_date: date) -> Any:
        response = self.client.request_json(
            "GET",
            f"{self.base_url}/mercado/boletin/ReporteResumenFinal",
            params={"fecha": report_date.isoformat()},
            headers={"x-api-key": self.api_key},
        )
        return response.data
