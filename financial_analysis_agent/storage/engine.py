"""DuckDB engine and schema initialization for the Financial Analysis Agent."""
import logging
from pathlib import Path
from typing import Optional

import duckdb

from ..config import get_config

logger = logging.getLogger(__name__)


class DuckDBEngine:
    """Manages DuckDB connection and database schema."""

    def __init__(self, db_path: Optional[str] = None):
        cfg = get_config()
        self.db_path = db_path or cfg.get("database.duckdb_path", "./data/financial.duckdb")
        # Ensure parent dir exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            logger.info(f"Connecting to DuckDB at {self.db_path}")
            self._conn = duckdb.connect(self.db_path)
            # Recommended pragmas for analytics-style workloads
            self._conn.execute("PRAGMA threads=4;")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            logger.info("Closing DuckDB connection")
            self._conn.close()
            self._conn = None

    def initialize_schema(self) -> None:
        """Create tables if they don't already exist."""
        logger.info("Initializing DuckDB schema (if not exists)")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                ticker TEXT PRIMARY KEY,
                name TEXT,
                sector TEXT,
                industry TEXT,
                market_cap DOUBLE,
                country TEXT
            );

            CREATE TABLE IF NOT EXISTS prices (
                ticker TEXT,
                date DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                PRIMARY KEY (ticker, date)
            );

            CREATE TABLE IF NOT EXISTS fundamentals (
                ticker TEXT,
                period_end DATE,
                period_type TEXT,
                revenue DOUBLE,
                gross_profit DOUBLE,
                opex DOUBLE,
                operating_income DOUBLE,
                net_income DOUBLE,
                assets DOUBLE,
                liabilities DOUBLE,
                equity DOUBLE,
                ocf DOUBLE,
                capex DOUBLE,
                PRIMARY KEY (ticker, period_end, period_type)
            );

            CREATE TABLE IF NOT EXISTS transcripts (
                ticker TEXT,
                event_date TIMESTAMP,
                speaker TEXT,
                role TEXT,
                text TEXT,
                source TEXT
            );

            CREATE TABLE IF NOT EXISTS social_agg (
                ticker TEXT,
                date DATE,
                platform TEXT,
                mentions INTEGER,
                avg_sentiment DOUBLE,
                pos_count INTEGER,
                neg_count INTEGER,
                neu_count INTEGER,
                PRIMARY KEY (ticker, date, platform)
            );

            CREATE TABLE IF NOT EXISTS news (
                ticker TEXT,
                published_at TIMESTAMP,
                publisher TEXT,
                title TEXT,
                link TEXT,
                sentiment DOUBLE
            );

            CREATE TABLE IF NOT EXISTS rankings (
                run_id TEXT,
                asof_date DATE,
                ticker TEXT,
                score DOUBLE,
                rank INTEGER,
                component_breakdown_json TEXT,
                PRIMARY KEY (run_id, ticker)
            );
            """
        )
        logger.info("Schema ready")
