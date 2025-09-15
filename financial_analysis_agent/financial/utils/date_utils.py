"""Date utilities for financial data processing."""

from typing import Optional
import pandas as pd


def parse_quarter_end(period: Optional[str]) -> Optional[pd.Timestamp]:
    """Parse quarter labels like '2025Q2' or '2025-Q2' to quarter end dates.
    
    Args:
        period: String representation of a quarter period (e.g., '2025Q2', '2025-Q2')
        
    Returns:
        Timestamp of the quarter end date or NaT if parsing fails
    """
    try:
        if not period or not isinstance(period, str):
            return pd.NaT
        s = period.strip().upper().replace(" ", "")
        # Accept forms like '2025Q2' or '2025-Q2'
        if "Q" in s:
            parts = s.replace("-", "")
            year = int(parts[:4])
            q = int(parts[5]) if len(parts) > 5 else int(parts.split("Q")[1])
            month_day = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}.get(q)
            if month_day:
                month, day = month_day
                return pd.Timestamp(year=year, month=month, day=day)
        # Fallback: try generic parser
        return pd.to_datetime(s, errors="coerce")
    except Exception:
        return pd.NaT
