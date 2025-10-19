"""DataFrame utilities for financial data processing."""

import logging
from typing import Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


def merge_estimates_on_period_end(
    base: pd.DataFrame, rev: pd.DataFrame
) -> pd.DataFrame:
    """Combine two estimate DataFrames on endDate/period, preferring exact date match then period label.

    Args:
        base: Base DataFrame containing estimates
        rev: Revenue DataFrame to merge with base

    Returns:
        Merged DataFrame with combined data
    """
    try:
        b = base.copy()
        r = rev.copy()
        # Ensure datetime
        if 'endDate' in b.columns:
            b['endDate'] = pd.to_datetime(b['endDate'], errors='coerce')
        if 'endDate' in r.columns:
            r['endDate'] = pd.to_datetime(r['endDate'], errors='coerce')

        # Add normalized period labels (YYYYQX) for better matching
        def _add_quarter_label(df):
            if 'endDate' in df.columns:
                df['_quarter_label'] = df['endDate'].apply(
                    lambda d: f"{d.year}Q{((d.month - 1)//3)+1}" if pd.notna(d) and hasattr(d, 'year') else None
                )
            return df

        b = _add_quarter_label(b)
        r = _add_quarter_label(r)

        # First, exact endDate merge
        merged = pd.merge(
            b,
            r[['endDate', 'revenueEstimateAvg']].dropna(subset=['endDate']).drop_duplicates('endDate'),
            on='endDate', how='left', suffixes=('', '_rev')
        )

        # If still missing revenueEstimateAvg, try quarter label join
        if ('revenueEstimateAvg' not in merged.columns) or (merged['revenueEstimateAvg'].isna().any()):
            if '_quarter_label' in b.columns and '_quarter_label' in r.columns:
                merged2 = pd.merge(
                    merged,
                    r[['_quarter_label', 'revenueEstimateAvg']].dropna(subset=['_quarter_label']).drop_duplicates('_quarter_label'),
                    on='_quarter_label', how='left', suffixes=('', '_qlabel')
                )
                # Fill missing with quarter-based
                if 'revenueEstimateAvg_qlabel' in merged2.columns:
                    merged2['revenueEstimateAvg'] = merged2['revenueEstimateAvg'].combine_first(merged2['revenueEstimateAvg_qlabel'])
                    merged = merged2.drop(columns=[c for c in merged2.columns if c.endswith('_qlabel')])

        # If still missing, try original period label join as fallback
        if ('revenueEstimateAvg' not in merged.columns) or (merged['revenueEstimateAvg'].isna().any()):
            if 'period' in b.columns and 'period' in r.columns:
                merged2 = pd.merge(
                    merged,
                    r[['period', 'revenueEstimateAvg']].dropna(subset=['period']).drop_duplicates('period'),
                    on='period', how='left', suffixes=('', '_rev_period')
                )
                # Fill missing with period-based
                if 'revenueEstimateAvg_rev_period' in merged2.columns:
                    merged2['revenueEstimateAvg'] = merged2['revenueEstimateAvg'].combine_first(merged2['revenueEstimateAvg_rev_period'])
                    merged = merged2.drop(columns=[c for c in merged2.columns if c.endswith('_rev_period')])

        # Clean up temporary columns
        merged = merged.drop(columns=[c for c in merged.columns if c.startswith('_quarter_label')])
        return merged
    except Exception as e:
        logger.warning(f"Failed to merge revenue estimates: {e}")
        return base


def normalize_column_names(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    """Normalize DataFrame column names based on a mapping.
    
    Args:
        df: DataFrame to normalize
        mapping: Dictionary mapping original column names to normalized names
        
    Returns:
        DataFrame with normalized column names
    """
    rename_dict = {col: mapping[col] for col in df.columns if col in mapping}
    if rename_dict:
        return df.rename(columns=rename_dict)
    return df
