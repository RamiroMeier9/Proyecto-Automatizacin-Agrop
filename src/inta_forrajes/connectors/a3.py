from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .utils import as_float
from ..http import HTTPClient
from ..models import A3Quote


class A3CredentialsError(RuntimeError):
    pass


def classify_cfi(cfi_code: str) -> str:
    first = (cfi_code or "").upper()[:1]
    if first == "F":
        return "future"
    if first == "O":
        return "option"
    return "unknown"


def _entry_value(market_data: dict[str, Any], key: str, field: str = "price") -> float | None:
    raw = market_data.get(key)
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if isinstance(raw, dict):
        raw = raw.get(field)
    return as_float(raw)


def _market_timestamp(market_data: dict[str, Any]) -> str:
    timestamps: list[float] = []
    for raw in market_data.values():
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            if isinstance(value, dict):
                timestamp = as_float(value.get("date"))
                if timestamp:
                    timestamps.append(timestamp)
    if not timestamps:
        return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(max(timestamps) / 1000, tz=timezone.utc).isoformat()


class A3Connector:
    def __init__(
        self,
        username: str,
        password: str,
        *,
        client: HTTPClient | None = None,
        auth_url: str | None = None,
        instruments_url: str | None = None,
        marketdata_url: str | None = None,
        market_id: str | None = None,
    ) -> None:
        if not username or not password:
            raise A3CredentialsError("A3 requiere usuario y contraseña habilitados para la API")
        self.username = username
        self.password = password
        self.client = client or HTTPClient()
        self.auth_url = auth_url or os.getenv(
            "A3_AUTH_URL", "https://api.remarkets.primary.com.ar/auth/getToken"
        )
        self.instruments_url = instruments_url or os.getenv(
            "A3_INSTRUMENTS_URL",
            "https://api.remarkets.primary.com.ar/rest/instruments/details",
        )
        self.marketdata_url = marketdata_url or os.getenv(
            "A3_MARKETDATA_URL",
            "https://api.remarkets.primary.com.ar/rest/marketdata/get",
        )
        self.market_id = market_id or os.getenv("A3_MARKET_ID", "ROFX")
        self._token: str | None = None

    def authenticate(self) -> str:
        response = self.client.request_json(
            "POST",
            self.auth_url,
            headers={"X-Username": self.username, "X-Password": self.password},
        )
        token = response.headers.get("x-auth-token")
        if not token and isinstance(response.data, dict):
            token = response.data.get("token") or response.data.get("x-auth-token")
        if not token:
            raise A3CredentialsError("A3 no devolvió el header X-Auth-Token")
        self._token = str(token)
        return self._token

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"X-Auth-Token": self._token or self.authenticate()}

    def fetch_instruments(self) -> list[dict]:
        response = self.client.request_json("GET", self.instruments_url, headers=self.auth_headers)
        if response.data.get("status") != "OK":
            raise RuntimeError(f"A3 devolvió estado {response.data.get('status')!r}")
        return list(response.data.get("instruments", []))

    def fetch_quote(self, symbol: str, metadata: dict[str, Any] | None = None) -> A3Quote:
        response = self.client.request_json(
            "GET",
            self.marketdata_url,
            headers=self.auth_headers,
            params={
                "marketId": self.market_id,
                "symbol": symbol,
                "entries": "BI,OF,LA,OP,CL,SE,OI,TV",
                "depth": 1,
            },
        )
        if response.data.get("status") != "OK":
            raise RuntimeError(f"No se pudo consultar {symbol}: {response.data}")
        market_data = response.data.get("marketData", {})
        info = metadata or {}
        return A3Quote(
            as_of=_market_timestamp(market_data),
            symbol=symbol,
            market_id=self.market_id,
            instrument_type=str(info.get("instrument_type") or classify_cfi(str(info.get("cficode", "")))),
            underlying=str(info.get("underlying", "")),
            maturity_date=str(info.get("maturity_date") or info.get("maturityDate") or ""),
            strike=as_float(info.get("strike")),
            option_type=str(info.get("option_type", "")),
            currency=str(info.get("currency", "")),
            unit=str(info.get("unit", "")),
            bid=_entry_value(market_data, "BI"),
            ask=_entry_value(market_data, "OF"),
            last=_entry_value(market_data, "LA"),
            settlement=_entry_value(market_data, "SE"),
            open_interest=_entry_value(market_data, "OI", field="size"),
            volume=_entry_value(market_data, "TV", field="size"),
            source_url=self.marketdata_url,
            metadata={"market_data": market_data},
        )

    def fetch_watchlist(self, watchlist: list[dict[str, Any]]) -> list[A3Quote]:
        quotes: list[A3Quote] = []
        for item in watchlist:
            enabled = str(item.get("enabled", "true")).strip().lower()
            if enabled not in {"1", "true", "yes", "si", "sí", "x"}:
                continue
            symbol = str(item.get("symbol", "")).strip()
            if symbol:
                quotes.append(self.fetch_quote(symbol, item))
        return quotes
