from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from .connectors.a3 import A3Connector
from .connectors.a3_marketdata import A3AgroMarketDataConnector, A3OfficialAPIKeyConnector
from .connectors.bcra import BCRAConnector
from .connectors.sio_granos import SIOGranosConnector
from .csv_io import (
    read_a3_quotes,
    read_alternatives,
    read_manual_prices,
    read_recipes,
    read_watchlist,
    write_instruments,
)
from .economics import evaluate_alternative
from .env import load_dotenv
from .models import A3Quote, EvaluationResult, PriceObservation
from .storage import Storage


PUBLIC_A3_SOURCE_URL = "https://marketdata.mae.com.ar/"


def _metadata(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_public_snapshot(prices: list[dict], quotes: list[dict]) -> dict:
    """Construye un archivo reproducible sólo con fuentes de acceso público."""
    public_prices = [
        {
            "observed_at": row["observed_at"],
            "series_id": row["series_id"],
            "item": row["item"],
            "value": row["value"],
            "currency": row["currency"],
            "unit": row["unit"],
            "source": row["source"],
            "source_url": row["source_url"],
            "ingestion_method": row["ingestion_method"],
            "metadata": _metadata(row.get("metadata_json", {})),
        }
        for row in prices
        if row.get("source") == "bcra"
    ]
    public_quotes = [
        {
            "as_of": row["as_of"],
            "symbol": row["symbol"],
            "market_id": row["market_id"],
            "instrument_type": row["instrument_type"],
            "underlying": row["underlying"],
            "maturity_date": row["maturity_date"],
            "strike": row["strike"],
            "option_type": row["option_type"],
            "currency": row["currency"],
            "unit": row["unit"],
            "bid": row["bid"],
            "ask": row["ask"],
            "last": row["last"],
            "settlement": row["settlement"],
            "open_interest": row["open_interest"],
            "volume": row["volume"],
            "source_url": row["source_url"],
            "ingestion_method": row["ingestion_method"],
            "metadata": _metadata(row.get("metadata_json", {})),
        }
        for row in quotes
        if row.get("source_url") == PUBLIC_A3_SOURCE_URL
    ]
    public_prices.sort(key=lambda row: (row["series_id"], row["observed_at"]))
    public_quotes.sort(key=lambda row: (row["underlying"], row["maturity_date"], row["symbol"]))
    return {
        "schema_version": 1,
        "latest_data_dates": {
            "bcra": max((row["observed_at"] for row in public_prices), default=None),
            "a3_public": max((row["as_of"] for row in public_quotes), default=None),
        },
        "prices": public_prices,
        "a3_quotes": public_quotes,
    }


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    @classmethod
    def discover(cls, root: str | Path | None = None) -> "ProjectPaths":
        project_root = Path(root) if root else Path(__file__).resolve().parents[2]
        return cls(project_root.resolve())

    @property
    def db(self) -> Path:
        configured = os.getenv("FORRAJES_DB", "data/forrajes.sqlite3")
        path = Path(configured)
        return path if path.is_absolute() else self.root / path

    @property
    def manual_dir(self) -> Path:
        return self.root / "data" / "manual"

    @property
    def watchlist(self) -> Path:
        return self.root / "config" / "a3_watchlist.csv"

    @property
    def snapshot(self) -> Path:
        return self.root / "data" / "snapshots" / "latest.json"

    @property
    def public_snapshot(self) -> Path:
        return self.root / "data" / "public" / "latest.json"

    @property
    def official_a3_snapshot(self) -> Path:
        """Respuesta autenticada de A3; nunca se versiona ni se publica."""
        return self.root / "data" / "snapshots" / "a3_official_latest.json"


class Pipeline:
    def __init__(self, root: str | Path | None = None) -> None:
        self.paths = ProjectPaths.discover(root)
        load_dotenv(self.paths.root / ".env")
        self.storage = Storage(self.paths.db)
        self.storage.initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _run_source(
        self,
        source: str,
        fetcher: Callable[[], list[PriceObservation] | list[A3Quote]],
        writer: Callable[[list], int],
    ) -> dict:
        started = self._now()
        try:
            rows = fetcher()
            count = writer(rows)
            status = "ok"
            message = ""
        except Exception as exc:  # La falla de una fuente no debe borrar las demás.
            count = 0
            status = "error"
            message = str(exc)
        finished = self._now()
        self.storage.log_sync(source, started, finished, status, count, message)
        return {"source": source, "status": status, "rows": count, "message": message}

    def import_manual(self) -> dict:
        started = self._now()
        prices, price_skipped = read_manual_prices(self.paths.manual_dir / "manual_prices.csv")
        quotes, quote_skipped = read_a3_quotes(self.paths.manual_dir / "a3_quotes.csv")
        price_count = self.storage.upsert_prices(prices)
        quote_count = self.storage.upsert_a3_quotes(quotes)
        finished = self._now()
        skipped = price_skipped + quote_skipped
        self.storage.log_sync(
            "manual_csv",
            started,
            finished,
            "ok",
            price_count + quote_count,
            f"{len(skipped)} filas incompletas omitidas",
        )
        return {
            "prices": price_count,
            "a3_quotes": quote_count,
            "skipped": skipped,
        }

    def _update_a3_official_report(self) -> dict:
        """Consulta la API-Key formal y conserva la respuesta fuera del repositorio."""
        api_key = os.getenv("A3_MD_API_KEY", "").strip()
        if not api_key:
            return {
                "source": "a3_marketdata_official",
                "status": "skipped",
                "rows": 0,
                "message": "falta A3_MD_API_KEY",
            }

        environment = os.getenv("A3_MD_ENV", "uat").strip().lower() or "uat"
        started = self._now()
        try:
            report_date = date.today()
            report = A3OfficialAPIKeyConnector(
                api_key,
                environment=environment,
            ).fetch_final_report(report_date)
            self.paths.official_a3_snapshot.parent.mkdir(parents=True, exist_ok=True)
            self.paths.official_a3_snapshot.write_text(
                json.dumps(
                    {
                        "generated_at": self._now(),
                        "report_date": report_date.isoformat(),
                        "environment": environment,
                        "data": report,
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
                + "\n",
                encoding="utf-8",
            )
            rows = len(report) if isinstance(report, list) else 1
            status = "ok"
            message = str(self.paths.official_a3_snapshot)
        except Exception as exc:
            rows = 0
            status = "error"
            message = str(exc)
        finished = self._now()
        self.storage.log_sync(
            "a3_marketdata_official",
            started,
            finished,
            status,
            rows,
            message,
        )
        return {
            "source": "a3_marketdata_official",
            "status": status,
            "rows": rows,
            "message": message,
        }

    def update(self, source: str = "all") -> list[dict]:
        requested = source.lower()
        results: list[dict] = []
        if requested in {"all", "bcra"}:
            results.append(
                self._run_source(
                    "bcra",
                    lambda: BCRAConnector().fetch_latest(),
                    self.storage.upsert_prices,
                )
            )

        if requested in {"all", "sio", "sio_granos"}:
            cuit, token = os.getenv("SIO_CUIT", ""), os.getenv("SIO_TOKEN", "")
            if cuit and token:
                results.append(
                    self._run_source(
                        "sio_granos",
                        lambda: SIOGranosConnector(cuit, token).fetch_latest_prices(),
                        self.storage.upsert_prices,
                    )
                )
            else:
                results.append({"source": "sio_granos", "status": "skipped", "rows": 0, "message": "faltan SIO_CUIT/SIO_TOKEN"})

        if requested in {"all", "a3"}:
            results.append(
                self._run_source(
                    "a3_agro_marketdata",
                    lambda: A3AgroMarketDataConnector().fetch_recent_quotes(),
                    self.storage.upsert_a3_quotes,
                )
            )
            results.append(self._update_a3_official_report())
            username, password = os.getenv("A3_USERNAME", ""), os.getenv("A3_PASSWORD", "")
            watchlist = read_watchlist(self.paths.watchlist)
            if username and password and watchlist:
                connector = A3Connector(username, password)
                results.append(
                    self._run_source(
                        "a3_trading_realtime",
                        lambda: connector.fetch_watchlist(watchlist),
                        self.storage.upsert_a3_quotes,
                    )
                )
        self.write_snapshot()
        return results

    def discover_a3(self) -> Path:
        username, password = os.getenv("A3_USERNAME", ""), os.getenv("A3_PASSWORD", "")
        connector = A3Connector(username, password)
        instruments = connector.fetch_instruments()
        output = self.paths.root / "data" / "a3_instruments.csv"
        write_instruments(output, instruments)
        return output

    def evaluate(
        self,
        alternative_id: str,
        annual_rate: float | None = None,
        yield_dm_kg_ha: float | None = None,
    ) -> EvaluationResult:
        alternatives = {
            alternative.alternative_id: alternative
            for alternative in read_alternatives(self.paths.manual_dir / "alternatives.csv")
        }
        if alternative_id not in alternatives:
            raise KeyError(f"Alternativa desconocida: {alternative_id}")
        settings = json.loads((self.paths.root / "config" / "settings.json").read_text(encoding="utf-8"))
        rate = float(annual_rate if annual_rate is not None else settings["project"]["discount_rate_annual"])
        recipe = read_recipes(self.paths.manual_dir / "recipes.csv")
        alternative = alternatives[alternative_id]
        if yield_dm_kg_ha is not None:
            alternative = replace(alternative, yield_dm_kg_ha=yield_dm_kg_ha)
        return evaluate_alternative(
            alternative,
            recipe,
            self.storage.latest_prices(),
            rate,
        )

    def write_snapshot(self) -> Path:
        self.paths.snapshot.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "generated_at": self._now(),
            "prices": self.storage.latest_prices(),
            "a3_quotes": self.storage.latest_a3_quotes(),
            "sync_status": self.storage.sync_status(),
        }
        self.paths.snapshot.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return self.paths.snapshot

    def write_public_snapshot(self) -> Path:
        """Publica sólo datos que pueden quedar versionados en un repositorio público."""
        self.paths.public_snapshot.parent.mkdir(parents=True, exist_ok=True)
        document = build_public_snapshot(
            self.storage.latest_prices(),
            self.storage.latest_a3_quotes(),
        )
        self.paths.public_snapshot.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return self.paths.public_snapshot

    def export_evaluations(self, annual_rate: float | None = None) -> list[dict]:
        alternatives = read_alternatives(self.paths.manual_dir / "alternatives.csv")
        results = [asdict(self.evaluate(item.alternative_id, annual_rate)) for item in alternatives]
        output = self.paths.root / "data" / "snapshots" / "evaluations.csv"
        output.parent.mkdir(parents=True, exist_ok=True)
        columns = [
            "alternative_id",
            "cost_complete",
            "present_value_cost_ha",
            "equivalent_annual_cost_ha",
            "annual_produced_dm_kg_ha",
            "cost_per_kg_produced_dm",
            "annual_usable_dm_kg_ha",
            "cost_per_kg_usable_dm",
            "cost_per_kg_meat_equivalent",
            "missing_inputs",
            "evaluated_at",
        ]
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for result in results:
                result["missing_inputs"] = " | ".join(result["missing_inputs"])
                writer.writerow({key: result.get(key) for key in columns})
        return results
