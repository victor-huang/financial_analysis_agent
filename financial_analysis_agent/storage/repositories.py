"""DuckDB repositories for persisting and querying domain data."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, date
from typing import Iterable, List, Optional, Dict, Any

import pandas as pd

from .engine import DuckDBEngine

logger = logging.getLogger(__name__)


@dataclass
class BaseRepository:
    engine: DuckDBEngine

    def _df_to_table(self, df: pd.DataFrame, table: str, mode: str = "append") -> None:
        if df is None or df.empty:
            return
        con = self.engine.conn
        # Create a temp view and insert to target
        con.register("_tmp_df", df)
        if mode == "append":
            con.execute(f"INSERT INTO {table} SELECT * FROM _tmp_df")
        elif mode == "replace":
            con.execute(f"DELETE FROM {table}")
            con.execute(f"INSERT INTO {table} SELECT * FROM _tmp_df")
        else:
            raise ValueError("Unsupported mode")
        con.unregister("_tmp_df")


class CompaniesRepository(BaseRepository):
    def upsert(self, rows: Iterable[Dict[str, Any]]) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)[["ticker", "name", "sector", "industry", "market_cap", "country"]]
        # Use INSERT OR REPLACE to respect primary key
        self.engine.conn.register("_tmp", df)
        self.engine.conn.execute(
            """
            INSERT OR REPLACE INTO companies
            SELECT * FROM _tmp
            """
        )
        self.engine.conn.unregister("_tmp")


class PricesRepository(BaseRepository):
    def upsert_prices(self, df: pd.DataFrame) -> None:
        # Expect columns: ticker,date,open,high,low,close,volume
        self.engine.conn.register("_tmp_prices", df)
        self.engine.conn.execute(
            """
            INSERT OR REPLACE INTO prices
            SELECT ticker, CAST(date AS DATE) AS date, open, high, low, close, volume
            FROM _tmp_prices
            """
        )
        self.engine.conn.unregister("_tmp_prices")

    def get_prices(self, ticker: str, start: Optional[date] = None, end: Optional[date] = None) -> pd.DataFrame:
        q = "SELECT * FROM prices WHERE ticker = ?"
        params: List[Any] = [ticker]
        if start is not None:
            q += " AND date >= ?"
            params.append(start)
        if end is not None:
            q += " AND date <= ?"
            params.append(end)
        q += " ORDER BY date"
        return self.engine.conn.execute(q, params).df()


class FundamentalsRepository(BaseRepository):
    def upsert(self, df: pd.DataFrame) -> None:
        # Expect columns aligned to schema and include ticker, period_end, period_type
        self.engine.conn.register("_tmp_fun", df)
        self.engine.conn.execute(
            """
            INSERT OR REPLACE INTO fundamentals
            SELECT ticker,
                   CAST(period_end AS DATE) AS period_end,
                   period_type,
                   revenue,
                   gross_profit,
                   opex,
                   operating_income,
                   net_income,
                   assets,
                   liabilities,
                   equity,
                   ocf,
                   capex
            FROM _tmp_fun
            """
        )
        self.engine.conn.unregister("_tmp_fun")

    def get(self, ticker: str, period_type: Optional[str] = None) -> pd.DataFrame:
        q = "SELECT * FROM fundamentals WHERE ticker = ?"
        params: List[Any] = [ticker]
        if period_type:
            q += " AND period_type = ?"
            params.append(period_type)
        q += " ORDER BY period_end DESC"
        return self.engine.conn.execute(q, params).df()


class TranscriptsRepository(BaseRepository):
    def upsert(self, rows: Iterable[Dict[str, Any]]) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)[["ticker", "event_date", "speaker", "role", "text", "source"]]
        self._df_to_table(df, "transcripts", mode="append")

    def get(self, ticker: str, start: Optional[datetime] = None, end: Optional[datetime] = None) -> pd.DataFrame:
        q = "SELECT * FROM transcripts WHERE ticker = ?"
        params: List[Any] = [ticker]
        if start is not None:
            q += " AND event_date >= ?"
            params.append(start)
        if end is not None:
            q += " AND event_date <= ?"
            params.append(end)
        q += " ORDER BY event_date DESC"
        return self.engine.conn.execute(q, params).df()


class SocialAggRepository(BaseRepository):
    def upsert(self, rows: Iterable[Dict[str, Any]]) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)[
            [
                "ticker",
                "date",
                "platform",
                "mentions",
                "avg_sentiment",
                "pos_count",
                "neg_count",
                "neu_count",
            ]
        ]
        self.engine.conn.register("_tmp_social", df)
        self.engine.conn.execute(
            """
            INSERT OR REPLACE INTO social_agg
            SELECT ticker,
                   CAST(date AS DATE) AS date,
                   platform,
                   mentions,
                   avg_sentiment,
                   pos_count,
                   neg_count,
                   neu_count
            FROM _tmp_social
            """
        )
        self.engine.conn.unregister("_tmp_social")

    def get(self, ticker: str, start: Optional[date] = None, end: Optional[date] = None) -> pd.DataFrame:
        q = "SELECT * FROM social_agg WHERE ticker = ?"
        params: List[Any] = [ticker]
        if start is not None:
            q += " AND date >= ?"
            params.append(start)
        if end is not None:
            q += " AND date <= ?"
            params.append(end)
        q += " ORDER BY date"
        return self.engine.conn.execute(q, params).df()


class NewsRepository(BaseRepository):
    def upsert(self, rows: Iterable[Dict[str, Any]]) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)[["ticker", "published_at", "publisher", "title", "link", "sentiment"]]
        self._df_to_table(df, "news", mode="append")

    def get(self, ticker: str, limit: int = 50) -> pd.DataFrame:
        q = "SELECT * FROM news WHERE ticker = ? ORDER BY published_at DESC LIMIT ?"
        return self.engine.conn.execute(q, [ticker, limit]).df()


class RankingsRepository(BaseRepository):
    def upsert(self, rows: Iterable[Dict[str, Any]]) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)[["run_id", "asof_date", "ticker", "score", "rank", "component_breakdown_json"]]
        self.engine.conn.register("_tmp_rank", df)
        self.engine.conn.execute(
            """
            INSERT OR REPLACE INTO rankings
            SELECT run_id,
                   CAST(asof_date AS DATE) AS asof_date,
                   ticker,
                   score,
                   rank,
                   component_breakdown_json
            FROM _tmp_rank
            """
        )
        self.engine.conn.unregister("_tmp_rank")

    def get_run(self, run_id: str) -> pd.DataFrame:
        return self.engine.conn.execute("SELECT * FROM rankings WHERE run_id = ? ORDER BY rank", [run_id]).df()

    def latest_by_date(self, asof_date: date) -> pd.DataFrame:
        q = """
        SELECT * FROM rankings
        WHERE asof_date = ?
        ORDER BY rank
        """
        return self.engine.conn.execute(q, [asof_date]).df()
