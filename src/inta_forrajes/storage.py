from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

from .models import A3Quote, PriceObservation


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS price_observations (
    id INTEGER PRIMARY KEY,
    observed_at TEXT NOT NULL,
    series_id TEXT NOT NULL,
    item TEXT NOT NULL,
    value REAL NOT NULL,
    currency TEXT NOT NULL,
    unit TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    ingestion_method TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(observed_at, series_id, source)
);

CREATE INDEX IF NOT EXISTS idx_prices_latest
ON price_observations(series_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS a3_quotes (
    id INTEGER PRIMARY KEY,
    as_of TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market_id TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    underlying TEXT NOT NULL DEFAULT '',
    maturity_date TEXT NOT NULL DEFAULT '',
    strike REAL,
    option_type TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL DEFAULT '',
    bid REAL,
    ask REAL,
    last REAL,
    settlement REAL,
    open_interest REAL,
    volume REAL,
    source_url TEXT NOT NULL DEFAULT '',
    ingestion_method TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(as_of, symbol, market_id)
);

CREATE INDEX IF NOT EXISTS idx_a3_quotes_latest
ON a3_quotes(symbol, as_of DESC);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL,
    rows_written INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT ''
);
"""


class Storage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def upsert_prices(self, observations: Sequence[PriceObservation]) -> int:
        if not observations:
            return 0
        sql = """
        INSERT INTO price_observations (
            observed_at, series_id, item, value, currency, unit, source,
            source_url, ingestion_method, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(observed_at, series_id, source) DO UPDATE SET
            item=excluded.item,
            value=excluded.value,
            currency=excluded.currency,
            unit=excluded.unit,
            source_url=excluded.source_url,
            ingestion_method=excluded.ingestion_method,
            metadata_json=excluded.metadata_json,
            ingested_at=CURRENT_TIMESTAMP
        """
        rows = [
            (
                item.observed_at,
                item.series_id,
                item.item,
                item.value,
                item.currency,
                item.unit,
                item.source,
                item.source_url,
                item.ingestion_method,
                json.dumps(item.metadata, ensure_ascii=False, sort_keys=True),
            )
            for item in observations
        ]
        with self.connect() as connection:
            connection.executemany(sql, rows)
        return len(rows)

    def upsert_a3_quotes(self, quotes: Sequence[A3Quote]) -> int:
        if not quotes:
            return 0
        sql = """
        INSERT INTO a3_quotes (
            as_of, symbol, market_id, instrument_type, underlying, maturity_date,
            strike, option_type, currency, unit, bid, ask, last, settlement,
            open_interest, volume, source_url, ingestion_method, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(as_of, symbol, market_id) DO UPDATE SET
            instrument_type=excluded.instrument_type,
            underlying=excluded.underlying,
            maturity_date=excluded.maturity_date,
            strike=excluded.strike,
            option_type=excluded.option_type,
            currency=excluded.currency,
            unit=excluded.unit,
            bid=excluded.bid,
            ask=excluded.ask,
            last=excluded.last,
            settlement=excluded.settlement,
            open_interest=excluded.open_interest,
            volume=excluded.volume,
            source_url=excluded.source_url,
            ingestion_method=excluded.ingestion_method,
            metadata_json=excluded.metadata_json,
            ingested_at=CURRENT_TIMESTAMP
        """
        rows = [
            (
                q.as_of,
                q.symbol,
                q.market_id,
                q.instrument_type,
                q.underlying,
                q.maturity_date,
                q.strike,
                q.option_type,
                q.currency,
                q.unit,
                q.bid,
                q.ask,
                q.last,
                q.settlement,
                q.open_interest,
                q.volume,
                q.source_url,
                q.ingestion_method,
                json.dumps(q.metadata, ensure_ascii=False, sort_keys=True),
            )
            for q in quotes
        ]
        with self.connect() as connection:
            connection.executemany(sql, rows)
        return len(rows)

    def latest_prices(self) -> list[dict]:
        query = """
        SELECT p.*
        FROM price_observations p
        JOIN (
            SELECT series_id, MAX(observed_at) AS max_date
            FROM price_observations
            GROUP BY series_id
        ) latest
          ON p.series_id = latest.series_id AND p.observed_at = latest.max_date
        ORDER BY p.series_id, p.source
        """
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query).fetchall()]

    def latest_a3_quotes(self) -> list[dict]:
        query = """
        SELECT q.*
        FROM a3_quotes q
        JOIN (
            SELECT symbol, market_id, MAX(as_of) AS max_date
            FROM a3_quotes
            GROUP BY symbol, market_id
        ) latest
          ON q.symbol = latest.symbol
         AND q.market_id = latest.market_id
         AND q.as_of = latest.max_date
        ORDER BY q.underlying, q.maturity_date, q.symbol
        """
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query).fetchall()]

    def log_sync(
        self,
        source: str,
        started_at: str,
        finished_at: str,
        status: str,
        rows_written: int,
        message: str = "",
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sync_log
                    (source, started_at, finished_at, status, rows_written, message)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (source, started_at, finished_at, status, rows_written, message),
            )

    def sync_status(self) -> list[dict]:
        query = """
        SELECT s.*
        FROM sync_log s
        JOIN (
            SELECT source, MAX(id) AS max_id FROM sync_log GROUP BY source
        ) latest ON s.id = latest.max_id
        ORDER BY s.source
        """
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query).fetchall()]
