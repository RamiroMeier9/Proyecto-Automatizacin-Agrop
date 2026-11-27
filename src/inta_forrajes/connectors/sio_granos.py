from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from .utils import as_float, slug
from ..http import HTTPClient
from ..models import PriceObservation


class SIOGranosConnector:
    endpoint = (
        "https://www.siogranos.com.ar/SiogranosAPI/api/"
        "ConsultaPublica/consultarOperaciones/"
    )

    def __init__(self, cuit: str, token: str, client: HTTPClient | None = None) -> None:
        if not cuit or not token:
            raise ValueError("SIO-Granos requiere CUIT y token")
        self.cuit = "".join(character for character in cuit if character.isdigit())
        self.token = token
        self.client = client or HTTPClient(timeout=45)

    def fetch_operations(self, *, days: int = 7, extra_params: dict[str, Any] | None = None) -> list[dict]:
        today = date.today()
        params: dict[str, Any] = {
            "CUITUsuarioApi": self.cuit,
            "tokenUsuarioApi": self.token,
            "fechaOperacionDesde": (today - timedelta(days=days)).isoformat(),
            "fechaOperacionHasta": today.isoformat(),
        }
        params.update(extra_params or {})
        response = self.client.request_json("GET", self.endpoint, params=params)
        if not response.data.get("success", False):
            raise RuntimeError(response.data.get("message", "SIO-Granos devolvió un error"))
        return list(response.data.get("result", {}).get("operaciones", []))

    def aggregate_vwap(self, operations: list[dict]) -> list[PriceObservation]:
        """Calcula un precio medio ponderado por volumen, sin mezclar moneda ni lugar."""
        groups: dict[tuple[str, str, str, str], list[tuple[float, float]]] = defaultdict(list)
        metadata: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for row in operations:
            price = as_float(row.get("precioTN"))
            volume = as_float(row.get("volumenTN"))
            if price is None or volume is None or volume <= 0:
                continue
            timestamp = str(row.get("fechaOperacion", ""))
            observed_at = timestamp[:10]
            grain = str(row.get("grano", "SIN_PRODUCTO")).strip().upper()
            delivery = str(row.get("lugarEntrega", "SIN_LUGAR")).strip()
            symbol = str(row.get("simboloPrecioPorTN", "")).strip()
            currency = "ARS" if symbol == "$" else "USD" if symbol.upper() in {"U$S", "USD"} else symbol
            key = (observed_at, grain, delivery, currency)
            groups[key].append((price, volume))
            metadata[key] = {
                "grain": grain,
                "delivery_place": delivery,
                "currency_symbol": symbol,
            }

        observations: list[PriceObservation] = []
        for (observed_at, grain, delivery, currency), values in groups.items():
            total_volume = sum(volume for _, volume in values)
            vwap = sum(price * volume for price, volume in values) / total_volume
            series_id = f"SIO_{slug(grain)}_{slug(delivery)}_{slug(currency)}"
            observations.append(
                PriceObservation(
                    observed_at=observed_at,
                    series_id=series_id,
                    item=f"{grain} — {delivery}",
                    value=vwap,
                    currency=currency or "N/D",
                    unit="por_tn",
                    source="sio_granos",
                    source_url=self.endpoint,
                    metadata={
                        **metadata[(observed_at, grain, delivery, currency)],
                        "operation_count": len(values),
                        "total_volume_tn": total_volume,
                        "aggregation": "volume_weighted_average",
                    },
                )
            )
        return observations

    def fetch_latest_prices(self, *, days: int = 7) -> list[PriceObservation]:
        return self.aggregate_vwap(self.fetch_operations(days=days))
