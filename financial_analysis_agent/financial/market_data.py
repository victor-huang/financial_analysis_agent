"""Market data analysis module for processing and analyzing stock market data."""
import logging
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

class MarketData:
    """Class for analyzing market data."""
    
    def __init__(self, ticker: str, data_fetcher=None):
        """Initialize with a ticker symbol and optional data fetcher."""
        self.ticker = ticker.upper()
        self.data_fetcher = data_fetcher
        self._price_data = None
        self._volume_data = None
        self._returns_data = None
    
    def load_price_data(
        self, 
        period: str = '1y',
        interval: str = '1d',
        start_date: str = None,
        end_date: str = None
    ) -> bool:
        """Load price data for the ticker."""
        try:
            if not self.data_fetcher:
                from .data_fetcher import FinancialDataFetcher
                self.data_fetcher = FinancialDataFetcher()
            
            df = self.data_fetcher.get_stock_data(
                self.ticker, 
                start_date=start_date,
                end_date=end_date,
                interval=interval,
                period=period
            )
            
            if df is None or df.empty:
                logger.error(f"No price data found for {self.ticker}")
                return False
            
            self._price_data = df
            self._calculate_returns()
            return True
            
        except Exception as e:
            logger.error(f"Error loading price data for {self.ticker}: {str(e)}")
            return False
    
    def _calculate_returns(self):
        """Calculate returns from price data."""
        if self._price_data is None or self._price_data.empty:
            return
        
        try:
            # Calculate daily returns
            if 'close' in self._price_data.columns:
                self._returns_data = pd.DataFrame()
                self._returns_data['daily_return'] = self._price_data['close'].pct_change()
                
                # Calculate additional return metrics
                self._returns_data['cumulative_return'] = (1 + self._returns_data['daily_return']).cumprod() - 1
                self._returns_data['log_return'] = np.log(1 + self._returns_data['daily_return'])
                
                # Calculate rolling metrics
                window = min(20, len(self._returns_data) // 2)  # Use a reasonable window size
                if window > 1:
                    self._returns_data['rolling_volatility'] = self._returns_data['daily_return'].rolling(window=window).std() * np.sqrt(252)  # Annualized
                    self._returns_data['rolling_sharpe'] = (self._returns_data['daily_return'].rolling(window=window).mean() * 252) / \
                                                         (self._returns_data['daily_return'].rolling(window=window).std() * np.sqrt(252) + 1e-9)
                
                # Calculate drawdown
                rolling_max = self._price_data['close'].cummax()
                self._returns_data['drawdown'] = self._price_data['close'] / rolling_max - 1.0
                
        except Exception as e:
            logger.error(f"Error calculating returns: {str(e)}")
    
    def get_technical_indicators(self) -> Dict[str, pd.Series]:
        """Calculate common technical indicators."""
        if self._price_data is None or self._price_data.empty:
            if not self.load_price_data():
                return {}
        
        try:
            indicators = {}
            df = self._price_data.copy()
            
            # Moving Averages
            df['SMA_20'] = df['close'].rolling(window=20).mean()
            df['SMA_50'] = df['close'].rolling(window=50).mean()
            df['SMA_200'] = df['close'].rolling(window=200).mean()
            
            # Exponential Moving Averages
            df['EMA_12'] = df['close'].ewm(span=12, adjust=False).mean()
            df['EMA_26'] = df['close'].ewm(span=26, adjust=False).mean()
            
            # MACD
            df['MACD'] = df['EMA_12'] - df['EMA_26']
            df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
            
            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / (loss + 1e-9)  # Avoid division by zero
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # Bollinger Bands
            df['BB_middle'] = df['close'].rolling(window=20).mean()
            df['BB_std'] = df['close'].rolling(window=20).std()
            df['BB_upper'] = df['BB_middle'] + (df['BB_std'] * 2)
            df['BB_lower'] = df['BB_middle'] - (df['BB_std'] * 2)
            
            # Drop NaN values
            df = df.dropna()
            
            # Convert to dictionary of series
            for col in df.columns:
                if col not in self._price_data.columns:  # Only include calculated indicators
                    indicators[col] = df[col]
            
            return indicators
            
        except Exception as e:
            logger.error(f"Error calculating technical indicators: {str(e)}")
            return {}
    
    def get_volatility_metrics(self, window: int = 20) -> Dict[str, float]:
        """Calculate volatility metrics."""
        if self._returns_data is None or self._returns_data.empty:
            if not self.load_price_data():
                return {}
        
        try:
            returns = self._returns_data['daily_return'].dropna()
            if len(returns) < 2:
                return {}
            
            # Calculate different volatility measures
            daily_volatility = returns.std()
            annualized_volatility = daily_volatility * np.sqrt(252)  # Trading days in a year
            
            # Rolling volatility
            rolling_vol = returns.rolling(window=min(window, len(returns))).std() * np.sqrt(252)
            
            # GARCH model for volatility clustering (simplified)
            # This is a simplified version - consider using arch library for full GARCH
            omega = 0.1
            alpha = 0.1
            beta = 0.8
            
            # Initialize variance
            variance = np.zeros_like(returns)
            variance[0] = returns.var()
            
            # GARCH(1,1) model
            for i in range(1, len(returns)):
                variance[i] = omega + alpha * (returns[i-1]**2) + beta * variance[i-1]
            
            garch_vol = np.sqrt(variance[-1] * 252)  # Annualized
            
            return {
                'daily_volatility': daily_volatility,
                'annualized_volatility': annualized_volatility,
                'current_rolling_volatility': rolling_vol.iloc[-1] if not rolling_vol.empty else None,
                'garch_volatility': garch_vol,
                'max_drawdown': self._returns_data['drawdown'].min() if 'drawdown' in self._returns_data.columns else None,
                'sharpe_ratio': self._calculate_sharpe_ratio()
            }
            
        except Exception as e:
            logger.error(f"Error calculating volatility metrics: {str(e)}")
            return {}
    
    def _calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> Optional[float]:
        """Calculate the Sharpe ratio."""
        if self._returns_data is None or 'daily_return' not in self._returns_data.columns:
            return None
        
        try:
            returns = self._returns_data['daily_return'].dropna()
            if len(returns) < 2:
                return None
                
            # Annualize the returns and standard deviation
            annualized_return = (1 + returns).prod() ** (252 / len(returns)) - 1
            annualized_vol = returns.std() * np.sqrt(252)
            
            # Calculate Sharpe ratio
            if annualized_vol > 0:
                return (annualized_return - risk_free_rate) / annualized_vol
            return 0.0
            
        except Exception as e:
            logger.error(f"Error calculating Sharpe ratio: {str(e)}")
            return None
    
    def get_price_moments(self) -> Dict[str, float]:
        """Calculate statistical moments of price returns."""
        if self._returns_data is None or 'daily_return' not in self._returns_data.columns:
            if not self.load_price_data():
                return {}
        
        try:
            returns = self._returns_data['daily_return'].dropna()
            if len(returns) < 2:
                return {}
            
            # Calculate moments
            mean = returns.mean()
            std = returns.std()
            skew = returns.skew()
            kurtosis = returns.kurtosis()
            
            # Jarque-Bera test for normality
            n = len(returns)
            jb_stat = n * (((skew ** 2) / 6) + ((kurtosis - 3) ** 2) / 24)
            # p-value for JB test (simplified)
            from scipy import stats
            jb_pvalue = 1 - stats.chi2.cdf(jb_stat, df=2)
            
            return {
                'mean_return': mean,
                'std_deviation': std,
                'skewness': skew,
                'kurtosis': kurtosis,
                'jarque_bera_stat': jb_stat,
                'jarque_bera_pvalue': jb_pvalue,
                'is_normal_distributed': jb_pvalue > 0.05  # 95% confidence
            }
            
        except Exception as e:
            logger.error(f"Error calculating price moments: {str(e)}")
            return {}
    
    def get_correlation_with_market(
        self, 
        market_ticker: str = '^GSPC',  # S&P 500
        period: str = '1y',
        interval: str = '1d'
    ) -> Dict[str, float]:
        """Calculate correlation with a market index."""
        try:
            # Load market data
            market_data = MarketData(market_ticker)
            if not market_data.load_price_data(period=period, interval=interval):
                return {}
            
            # Ensure we have our own data
            if self._price_data is None or self._price_data.empty:
                if not self.load_price_data(period=period, interval=interval):
                    return {}
            
            # Align the data
            aligned_data = pd.DataFrame({
                'ticker': self._price_data['close'],
                'market': market_data._price_data['close']
            }).dropna()
            
            if len(aligned_data) < 2:
                return {}
            
            # Calculate returns
            returns = aligned_data.pct_change().dropna()
            
            # Calculate correlation and beta
            correlation = returns['ticker'].corr(returns['market'])
            covariance = returns['ticker'].cov(returns['market'])
            market_variance = returns['market'].var()
            beta = covariance / market_variance if market_variance > 0 else 0
            
            # Calculate alpha (simplified)
            risk_free_rate = 0.02 / 252  # Daily risk-free rate
            excess_returns = returns - risk_free_rate
            alpha = excess_returns['ticker'].mean() - beta * excess_returns['market'].mean()
            
            return {
                'correlation': correlation,
                'beta': beta,
                'alpha': alpha * 252,  # Annualized
                'r_squared': correlation ** 2,
                'market_volatility': returns['market'].std() * np.sqrt(252),  # Annualized
                'tracking_error': (returns['ticker'] - returns['market']).std() * np.sqrt(252)  # Annualized
            }
            
        except Exception as e:
            logger.error(f"Error calculating market correlation: {str(e)}")
            return {}
    
    def get_support_resistance_levels(self, window: int = 20) -> Dict[str, float]:
        """Identify support and resistance levels."""
        if self._price_data is None or self._price_data.empty:
            if not self.load_price_data():
                return {}
        
        try:
            df = self._price_data.copy()
            if len(df) < window * 2:  # Need enough data
                return {}
            
            # Find local maxima and minima
            df['high_roll_max'] = df['high'].rolling(window=window, center=True).max()
            df['low_roll_min'] = df['low'].rolling(window=window, center=True).min()
            
            # Identify support and resistance levels
            resistance = df[df['high'] == df['high_roll_max']]['high']
            support = df[df['low'] == df['low_roll_min']]['low']
            
            # Get recent levels (last 20% of data)
            recent_data = df.iloc[-int(len(df) * 0.2):]
            recent_resistance = resistance[resistance.index.isin(recent_data.index)]
            recent_support = support[support.index.isin(recent_data.index)]
            
            # Get current price
            current_price = df['close'].iloc[-1]
            
            # Find nearest support and resistance
            if not recent_support.empty:
                support_levels = sorted(recent_support.unique(), reverse=True)  # Descending
                nearest_support = next((s for s in support_levels if s < current_price), None)
                next_support = next((s for s in reversed(support_levels) if s < current_price), None)
            else:
                nearest_support = next_support = None
            
            if not recent_resistance.empty:
                resistance_levels = sorted(recent_resistance.unique())  # Ascending
                nearest_resistance = next((r for r in resistance_levels if r > current_price), None)
                next_resistance = next((r for r in resistance_levels if r > current_price and (nearest_resistance is None or r > nearest_resistance)), None)
            else:
                nearest_resistance = next_resistance = None
            
            return {
                'current_price': current_price,
                'nearest_support': nearest_support,
                'next_support': next_support,
                'nearest_resistance': nearest_resistance,
                'next_resistance': next_resistance,
                'support_levels': sorted(support.unique().tolist(), reverse=True)[:5],  # Top 5 support levels
                'resistance_levels': sorted(resistance.unique().tolist())[:5]  # Top 5 resistance levels
            }
            
        except Exception as e:
            logger.error(f"Error identifying support/resistance levels: {str(e)}")
            return {}
