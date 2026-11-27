from __future__ import annotations

from .utils import as_float
from ..http import HTTPClient
from ..models import PriceObservation


class BCRAConnector:
    base_url = "https://api.bcra.gob.ar/estadisticascambiarias/v1.0/Cotizaciones"

    def __init__(self, client: HTTPClient | None = None) -> None:
        self.client = client or HTTPClient()

    def fetch_latest(self, currencies: tuple[str, ...] = ("USD", "EUR")) -> list[PriceObservation]:
        response = self.client.request_json("GET", self.base_url)
        results = response.data.get("results", {})
        observed_at = str(results.get("fecha") or "")
        if not observed_at:
            return []
        wanted = {currency.upper() for currency in currencies}
        observations: list[PriceObservation] = []
        for row in results.get("detalle", []):
            code = str(row.get("codigoMoneda", "")).upper()
            if code not in wanted:
                continue
            value = as_float(row.get("tipoCotizacion"))
            if value is None or value <= 0:
                continue
            observations.append(
                PriceObservation(
                    observed_at=observed_at,
                    series_id=f"FX_BCRA_{code}_ARS",
                    item=f"Tipo de cambio BCRA {code}",
                    value=value,
                    currency="ARS",
                    unit=f"ARS/{code}",
                    source="bcra",
                    source_url=self.base_url,
                    metadata={"tipo_pase": row.get("tipoPase"), "descripcion": row.get("descripcion")},
                )
            )
        return observations
