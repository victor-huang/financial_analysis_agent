"""Main analysis module for financial and social media data."""
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import json
import numpy as np
import pandas as pd

from .financial import FinancialDataFetcher, CompanyFundamentals, MarketData
from .social import TwitterClient, RedditClient
from .llm import OpenAIClient, HuggingFaceClient
from .config import get_config

logger = logging.getLogger(__name__)

def _to_jsonable(obj: Any) -> Any:
    """Recursively convert numpy/pandas objects into JSON-serializable Python types.
    - numpy scalars -> Python scalars
    - numpy arrays -> lists
    - pandas Series -> dict of index->value
    - pandas DataFrame -> list of records
    - pandas Timestamp/Datetime -> ISO string
    - sets/tuples -> lists
    """
    # None or basic types
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    # NaN/inf handling
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj

    # numpy scalars
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        val = float(obj)
        return None if (np.isnan(val) or np.isinf(val)) else val
    if isinstance(obj, (np.bool_,)):
        return bool(obj)

    # numpy arrays
    if isinstance(obj, np.ndarray):
        return [_to_jsonable(x) for x in obj.tolist()]

    # pandas types
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, pd.Series):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, pd.DataFrame):
        # include index as string if it's datetime-like
        df = obj.copy()
        if df.index.name is None:
            df = df.reset_index()
        return [_to_jsonable(rec) for rec in df.to_dict(orient='records')]

    # dict
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}

    # list/tuple/set
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(x) for x in obj]

    # fallback to string
    try:
        return str(obj)
    except Exception:
        return None

class FinancialAnalysisAgent:
    """Main class for financial and social media analysis."""
    
    def __init__(self, config_path: str = None):
        """Initialize the analysis agent."""
        self.config = get_config()
        
        # Initialize API clients
        self.financial_data = FinancialDataFetcher()
        self.twitter = TwitterClient()
        self.reddit = RedditClient()
        
        # Initialize LLM client (default to OpenAI)
        self.llm = self._initialize_llm()
        
        # Cache for storing analysis results
        self.cache = {}
    
    def _initialize_llm(self):
        """Initialize the appropriate LLM client based on configuration."""
        llm_config = self.config.get('llm', {})
        llm_type = llm_config.get('type', 'openai')
        
        if llm_type == 'openai':
            return OpenAIClient()
        elif llm_type == 'huggingface':
            return HuggingFaceClient(
                model_name=llm_config.get('model_name'),
                model_path=llm_config.get('model_path'),
                device=llm_config.get('device')
            )
        else:
            logger.warning(f"Unknown LLM type: {llm_type}. Defaulting to OpenAI.")
            return OpenAIClient()
    
    def analyze_company(
        self, 
        ticker: str, 
        analysis_type: str = "full",
        **kwargs
    ) -> Dict[str, Any]:
        """Analyze a company's financial and social data.
        
        Args:
            ticker: Company ticker symbol
            analysis_type: Type of analysis to perform ('financial', 'social', 'sentiment', 'full')
            **kwargs: Additional parameters for the analysis
            
        Returns:
            Dictionary with analysis results
        """
        try:
            ticker = ticker.upper()
            logger.info(f"Starting {analysis_type} analysis for {ticker}")
            
            result = {
                'ticker': ticker,
                'timestamp': datetime.utcnow().isoformat(),
                'analysis_type': analysis_type
            }
            
            # Perform financial analysis
            if analysis_type in ['financial', 'full']:
                result['financial'] = self._analyze_financials(ticker, **kwargs)
            
            # Perform social media analysis
            if analysis_type in ['social', 'sentiment', 'full']:
                result['social'] = self._analyze_social_media(ticker, **kwargs)
            
            # Perform sentiment analysis
            if analysis_type in ['sentiment', 'full'] and 'social' in result:
                result['sentiment'] = self._analyze_sentiment(
                    ticker, 
                    result.get('social', {}), 
                    **kwargs
                )
            
            # Generate summary using LLM
            if analysis_type in ['full']:
                result['summary'] = self._generate_summary(ticker, result, **kwargs)

            # Ensure JSON-serializable structure
            return _to_jsonable(result)
            
        except Exception as e:
            logger.error(f"Error analyzing company {ticker}: {str(e)}")
            return {
                'ticker': ticker,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def _analyze_financials(
        self, 
        ticker: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """Analyze company financials."""
        try:
            # Get company info
            company = CompanyFundamentals(ticker, self.financial_data)
            
            # Load financial statements
            if not company.load_financials():
                raise ValueError(f"Could not load financials for {ticker}")
            
            # Get key metrics (support annual or quarterly via kwarg)
            financial_period = kwargs.get('financial_period', 'annual')
            ratios = company.get_financial_ratios(period=financial_period)
            # Annual history (backward compatible)
            historical_ratios = company.get_historical_ratios()
            # Recent quarterly ratios (last 8 quarters)
            quarterly_ratios = company.get_periodic_ratios(period='quarterly', count=8)
            financial_health = company.analyze_financial_health()
            
            # Get market data
            market_data = MarketData(ticker, self.financial_data)
            market_data.load_price_data(period="1y")
            
            # Get technical indicators
            technicals = market_data.get_technical_indicators()
            volatility = market_data.get_volatility_metrics()
            price_moments = market_data.get_price_moments()
            
            # Get correlation with market
            market_correlation = market_data.get_correlation_with_market()
            
            # Get support/resistance levels
            support_resistance = market_data.get_support_resistance_levels()
            
            return {
                'company_info': self.financial_data.get_company_info(ticker),
                'financial_ratios': ratios,
                'historical_ratios': {
                    'annual': historical_ratios,
                    'quarterly': quarterly_ratios
                },
                'financial_health': financial_health,
                'technical_indicators': technicals,
                'volatility_metrics': volatility,
                'price_moments': price_moments,
                'market_correlation': market_correlation,
                'support_resistance': support_resistance,
                'last_updated': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing financials for {ticker}: {str(e)}")
            return {
                'error': str(e),
                'last_updated': datetime.utcnow().isoformat()
            }
    
    def _analyze_social_media(
        self, 
        ticker: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """Analyze social media data for a company."""
        try:
            result = {
                'ticker': ticker,
                'timestamp': datetime.utcnow().isoformat(),
                'sources': {}
            }
            
            # Get Twitter data
            try:
                twitter_sentiment = self.twitter.get_financial_sentiment(ticker, **kwargs)
                result['sources']['twitter'] = twitter_sentiment
            except Exception as e:
                logger.warning(f"Error getting Twitter data for {ticker}: {str(e)}")
                result['sources']['twitter'] = {'error': str(e)}
            
            # Get Reddit data
            try:
                reddit_sentiment = self.reddit.get_financial_sentiment(ticker, **kwargs)
                result['sources']['reddit'] = reddit_sentiment
            except Exception as e:
                logger.warning(f"Error getting Reddit data for {ticker}: {str(e)}")
                result['sources']['reddit'] = {'error': str(e)}
            
            # Calculate overall sentiment
            result['overall_sentiment'] = self._calculate_overall_sentiment(result['sources'])
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing social media for {ticker}: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def _calculate_overall_sentiment(self, sources: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall sentiment from multiple sources."""
        try:
            sentiments = []
            weights = {
                'twitter': 0.5,
                'reddit': 0.5
            }
            
            # Collect sentiment scores from each source
            for source, data in sources.items():
                if 'sentiment' in data and 'compound' in data['sentiment']:
                    sentiments.append({
                        'source': source,
                        'score': data['sentiment']['compound'],
                        'weight': weights.get(source, 0.3)
                    })
            
            if not sentiments:
                return {
                    'score': 0.0,
                    'label': 'neutral',
                    'sources': []
                }
            
            # Calculate weighted average sentiment
            total_weight = sum(s['weight'] for s in sentiments)
            if total_weight == 0:
                total_weight = 1.0
            
            weighted_sum = sum(s['score'] * s['weight'] for s in sentiments)
            avg_sentiment = weighted_sum / total_weight
            
            # Determine sentiment label
            if avg_sentiment >= 0.1:
                label = 'positive'
            elif avg_sentiment <= -0.1:
                label = 'negative'
            else:
                label = 'neutral'
            
            return {
                'score': avg_sentiment,
                'label': label,
                'sources': [{
                    'source': s['source'],
                    'score': s['score'],
                    'weight': s['weight']
                } for s in sentiments]
            }
            
        except Exception as e:
            logger.error(f"Error calculating overall sentiment: {str(e)}")
            return {
                'score': 0.0,
                'label': 'neutral',
                'error': str(e)
            }
    
    def _analyze_sentiment(
        self, 
        ticker: str, 
        social_data: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Perform in-depth sentiment analysis using LLM."""
        try:
            # Extract relevant text from social data
            texts = []
            
            # Get Twitter texts
            if 'twitter' in social_data.get('sources', {}):
                twitter_data = social_data['sources']['twitter']
                if 'tweet_samples' in twitter_data:
                    for tweet in twitter_data['tweet_samples']:
                        if 'text' in tweet:
                            texts.append({
                                'source': 'twitter',
                                'text': tweet['text'],
                                'sentiment': tweet.get('sentiment', 0.0)
                            })
            
            # Get Reddit texts
            if 'reddit' in social_data.get('sources', {}):
                reddit_data = social_data['sources']['reddit']
                if 'top_posts' in reddit_data:
                    for post in reddit_data['top_posts']:
                        if 'title' in post:
                            texts.append({
                                'source': 'reddit',
                                'text': post['title'],
                                'sentiment': post.get('sentiment', 0.0)
                            })
            
            if not texts:
                return {
                    'error': 'No text data available for sentiment analysis',
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            # Use LLM to analyze sentiment
            prompt = f"""
            Analyze the sentiment of the following social media posts about {ticker}.
            For each post, provide a sentiment score between -1 (very negative) and 1 (very positive),
            along with a brief explanation of your reasoning.
            
            Return a JSON array with the following structure for each post:
            [
                {{
                    "text": "the original text",
                    "sentiment_score": number between -1 and 1,
                    "explanation": "brief explanation of the sentiment",
                    "key_phrases": ["list", "of", "key", "phrases"]
                }},
                ...
            ]
            
            Posts to analyze:
            {json.dumps([t['text'] for t in texts], indent=2)}
            """
            
            # Generate analysis using LLM
            response = self.llm.generate(
                prompt=prompt,
                max_tokens=2000,
                temperature=0.3
            )
            
            # Parse the response
            try:
                analyses = json.loads(response)
                
                # Calculate overall sentiment
                if analyses:
                    avg_sentiment = sum(a.get('sentiment_score', 0) for a in analyses) / len(analyses)
                    
                    # Count sentiment categories
                    sentiment_counts = {
                        'positive': 0,
                        'neutral': 0,
                        'negative': 0
                    }
                    
                    for a in analyses:
                        score = a.get('sentiment_score', 0)
                        if score >= 0.1:
                            sentiment_counts['positive'] += 1
                        elif score <= -0.1:
                            sentiment_counts['negative'] += 1
                        else:
                            sentiment_counts['neutral'] += 1
                    
                    # Get most common key phrases
                    from collections import Counter
                    all_phrases = [
                        phrase.lower()
                        for a in analyses
                        for phrase in a.get('key_phrases', [])
                    ]
                    common_phrases = Counter(all_phrases).most_common(10)
                    
                    return {
                        'average_sentiment': avg_sentiment,
                        'sentiment_distribution': sentiment_counts,
                        'common_phrases': [{'phrase': p[0], 'count': p[1]} for p in common_phrases],
                        'analyses': analyses,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                
                return {
                    'error': 'No analyses returned',
                    'timestamp': datetime.utcnow().isoformat()
                }
                
            except json.JSONDecodeError:
                logger.error("Failed to parse sentiment analysis response")
                return {
                    'error': 'Failed to parse sentiment analysis',
                    'response': response,
                    'timestamp': datetime.utcnow().isoformat()
                }
            
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def _generate_summary(
        self, 
        ticker: str, 
        analysis_data: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Generate a summary of the analysis using LLM."""
        try:
            # Prepare data for the LLM
            summary_data = {
                'ticker': ticker,
                'company_info': analysis_data.get('financial', {}).get('company_info', {}),
                'financial_health': analysis_data.get('financial', {}).get('financial_health', {}),
                'market_data': {
                    'volatility': analysis_data.get('financial', {}).get('volatility_metrics', {}),
                    'support_resistance': analysis_data.get('financial', {}).get('support_resistance', {})
                },
                'sentiment': analysis_data.get('sentiment', {})
            }
            
            # Generate summary using LLM
            prompt = f"""
            You are a financial analyst preparing a comprehensive report on {ticker}.
            
            Based on the following analysis, provide a detailed summary that includes:
            1. Company overview
            2. Financial health assessment
            3. Market performance and technical analysis
            4. Social media sentiment analysis
            5. Overall investment recommendation
            
            Analysis Data:
            {json.dumps(summary_data, indent=2)}
            
            Your report should be well-structured, objective, and data-driven.
            Use clear section headers and bullet points where appropriate.
            """
            
            summary = self.llm.generate(
                prompt=prompt,
                max_tokens=2000,
                temperature=0.5
            )
            
            return {
                'summary': summary,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }


def main():
    """Main function for command-line usage."""
    import argparse
    import json
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Financial Analysis Agent')
    parser.add_argument('ticker', type=str, help='Stock ticker symbol')
    parser.add_argument('--analysis-type', type=str, default='full',
                        choices=['financial', 'social', 'sentiment', 'full'],
                        help='Type of analysis to perform')
    parser.add_argument('--output', type=str, help='Output file (JSON)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--financial-period', type=str, choices=['annual','quarterly'], default='annual',
                        help='Use latest annual or quarterly statements for ratios')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Initialize the agent
        agent = FinancialAnalysisAgent()
        
        # Run the analysis
        result = agent.analyze_company(
            ticker=args.ticker,
            analysis_type=args.analysis_type,
            financial_period=args.financial_period
        )
        
        # Output the results
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"Analysis saved to {args.output}")
        else:
            print(json.dumps(result, indent=2))
        
        return 0
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
