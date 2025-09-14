"""Twitter client for fetching and analyzing tweets related to financial instruments."""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import tweepy
import pandas as pd
import pytz

from ..config import get_config

logger = logging.getLogger(__name__)

class TwitterClient:
    """Client for interacting with Twitter API."""
    
    def __init__(self, api_key: str = None, api_secret: str = None, 
                 access_token: str = None, access_token_secret: str = None):
        """Initialize Twitter client with API credentials."""
        self.config = get_config()
        
        # Use provided credentials or fall back to config
        self.api_key = api_key or self.config.get('apis.twitter.api_key')
        self.api_secret = api_secret or self.config.get('apis.twitter.api_secret')
        self.access_token = access_token or self.config.get('apis.twitter.access_token')
        self.access_token_secret = access_token_secret or self.config.get('apis.twitter.access_token_secret')
        
        self.client = None
        self.authenticate()
    
    def authenticate(self) -> bool:
        """Authenticate with Twitter API."""
        try:
            if not all([self.api_key, self.api_secret, self.access_token, self.access_token_secret]):
                logger.warning("Twitter API credentials not fully configured")
                return False
                
            # Use OAuth 1.0a User Context for v1.1 API
            auth = tweepy.OAuth1UserHandler(
                self.api_key,
                self.api_secret,
                self.access_token,
                self.access_token_secret
            )
            
            # Create API client
            self.client = tweepy.API(
                auth,
                wait_on_rate_limit=True,
                retry_count=3,
                retry_delay=5,
                retry_errors={401, 404, 500, 502, 503, 504}
            )
            
            # Verify credentials
            self.client.verify_credentials()
            logger.info("Successfully authenticated with Twitter API")
            return True
            
        except Exception as e:
            logger.error(f"Twitter authentication failed: {str(e)}")
            self.client = None
            return False
    
    def search_tweets(
        self, 
        query: str, 
        max_results: int = 100,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        lang: str = 'en'
    ) -> List[Dict]:
        """Search for tweets matching a query.
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return (1-100)
            since: Return tweets after this datetime
            until: Return tweets before this datetime
            lang: Language code (e.g., 'en' for English)
            
        Returns:
            List of tweet dictionaries
        """
        if not self.client:
            logger.error("Twitter client not authenticated")
            return []
        
        try:
            # Format dates for Twitter API
            since_str = since.strftime('%Y-%m-%d') if since else None
            until_str = until.strftime('%Y-%m-%d') if until else None
            
            # Build search parameters
            search_params = {
                'q': query,
                'count': min(max_results, 100),  # Max 100 per request
                'tweet_mode': 'extended',
                'lang': lang,
                'since': since_str,
                'until': until_str
            }
            
            # Remove None values
            search_params = {k: v for k, v in search_params.items() if v is not None}
            
            # Execute search
            tweets = []
            for tweet in tweepy.Cursor(
                self.client.search_tweets,
                **search_params
            ).items(max_results):
                tweets.append(self._parse_tweet(tweet))
                
            logger.info(f"Retrieved {len(tweets)} tweets for query: {query}")
            return tweets
            
        except Exception as e:
            logger.error(f"Error searching tweets: {str(e)}")
            return []
    
    def get_trending_topics(self, woeid: int = 1) -> List[Dict]:
        """Get trending topics for a specific location.
        
        Args:
            woeid: Where On Earth ID (1 = Worldwide)
            
        Returns:
            List of trending topics with details
        """
        if not self.client:
            logger.error("Twitter client not authenticated")
            return []
        
        try:
            trends = self.client.get_place_trends(woeid)
            return [{
                'name': trend['name'],
                'url': trend['url'],
                'tweet_volume': trend.get('tweet_volume'),
                'promoted_content': trend.get('promoted_content')
            } for trend in trends[0]['trends']]
            
        except Exception as e:
            logger.error(f"Error getting trending topics: {str(e)}")
            return []
    
    def get_user_timeline(
        self, 
        username: str, 
        count: int = 20,
        include_rts: bool = False,
        exclude_replies: bool = True
    ) -> List[Dict]:
        """Get tweets from a user's timeline.
        
        Args:
            username: Twitter username (without @)
            count: Number of tweets to retrieve (1-200)
            include_rts: Include retweets
            exclude_replies: Exclude replies
            
        Returns:
            List of tweet dictionaries
        """
        if not self.client:
            logger.error("Twitter client not authenticated")
            return []
        
        try:
            tweets = self.client.user_timeline(
                screen_name=username,
                count=min(count, 200),
                tweet_mode='extended',
                include_rts=include_rts,
                exclude_replies=exclude_replies
            )
            
            return [self._parse_tweet(tweet) for tweet in tweets]
            
        except Exception as e:
            logger.error(f"Error getting user timeline for @{username}: {str(e)}")
            return []
    
    def get_tweet_metrics(self, tweet_id: str) -> Optional[Dict]:
        """Get engagement metrics for a specific tweet.
        
        Args:
            tweet_id: ID of the tweet
            
        Returns:
            Dictionary with engagement metrics
        """
        if not self.client:
            logger.error("Twitter client not authenticated")
            return None
        
        try:
            tweet = self.client.get_status(tweet_id, tweet_mode='extended')
            return {
                'retweets': tweet.retweet_count,
                'favorites': tweet.favorite_count,
                'replies': tweet.reply_count if hasattr(tweet, 'reply_count') else 0,
                'quotes': tweet.quote_count if hasattr(tweet, 'quote_count') else 0,
                'impressions': tweet.view_count if hasattr(tweet, 'view_count') else None,
                'engagement_rate': self._calculate_engagement_rate(tweet)
            }
            
        except Exception as e:
            logger.error(f"Error getting metrics for tweet {tweet_id}: {str(e)}")
            return None
    
    def _parse_tweet(self, tweet) -> Dict:
        """Parse tweet object into a dictionary."""
        if hasattr(tweet, 'retweeted_status'):
            # This is a retweet, get the original tweet
            original_tweet = tweet.retweeted_status
            text = original_tweet.full_text if hasattr(original_tweet, 'full_text') else original_tweet.text
            is_retweet = True
        else:
            text = tweet.full_text if hasattr(tweet, 'full_text') else tweet.text
            is_retweet = False
        
        return {
            'id': str(tweet.id),
            'created_at': tweet.created_at,
            'text': text,
            'user': {
                'id': tweet.user.id,
                'name': tweet.user.name,
                'screen_name': tweet.user.screen_name,
                'followers_count': tweet.user.followers_count,
                'friends_count': tweet.user.friends_count,
                'verified': tweet.user.verified
            },
            'is_retweet': is_retweet,
            'retweet_count': tweet.retweet_count,
            'favorite_count': tweet.favorite_count,
            'lang': tweet.lang,
            'hashtags': [h['text'] for h in tweet.entities['hashtags']],
            'user_mentions': [m['screen_name'] for m in tweet.entities['user_mentions']],
            'urls': [u['expanded_url'] for u in tweet.entities['urls']],
            'media': [m['media_url_https'] for m in tweet.entities.get('media', [])]
        }
    
    def _calculate_engagement_rate(self, tweet) -> float:
        """Calculate engagement rate for a tweet."""
        try:
            if not hasattr(tweet, 'user') or not hasattr(tweet.user, 'followers_count'):
                return 0.0
                
            if tweet.user.followers_count == 0:
                return 0.0
                
            engagements = (
                tweet.favorite_count + 
                tweet.retweet_count + 
                (tweet.reply_count if hasattr(tweet, 'reply_count') else 0) + 
                (tweet.quote_count if hasattr(tweet, 'quote_count') else 0)
            )
            
            return (engagements / tweet.user.followers_count) * 100
            
        except Exception as e:
            logger.error(f"Error calculating engagement rate: {str(e)}")
            return 0.0
    
    def get_financial_sentiment(
        self, 
        ticker: str, 
        days: int = 7, 
        max_tweets: int = 200
    ) -> Dict:
        """Analyze sentiment of tweets about a financial instrument.
        
        Args:
            ticker: Stock/crypto ticker symbol
            days: Number of days to look back
            max_tweets: Maximum number of tweets to analyze
            
        Returns:
            Dictionary with sentiment analysis results
        """
        try:
            # Search for tweets about the ticker
            since = datetime.now() - timedelta(days=days)
            query = f"${ticker} OR #{ticker} OR {ticker} stock"
            
            tweets = self.search_tweets(
                query=query,
                max_results=min(max_tweets, 200),
                since=since,
                lang='en'
            )
            
            if not tweets:
                return {
                    'ticker': ticker,
                    'tweet_count': 0,
                    'error': 'No tweets found'
                }
            
            # Analyze sentiment
            from .sentiment_analyzer import SentimentAnalyzer
            analyzer = SentimentAnalyzer()
            
            results = {
                'ticker': ticker,
                'tweet_count': len(tweets),
                'time_period': {
                    'start': min(t['created_at'] for t in tweets),
                    'end': max(t['created_at'] for t in tweets)
                },
                'sentiment_scores': [],
                'average_sentiment': 0.0,
                'positive_tweets': 0,
                'neutral_tweets': 0,
                'negative_tweets': 0,
                'top_influencers': [],
                'tweet_samples': []
            }
            
            # Process each tweet
            for tweet in tweets:
                # Get sentiment
                sentiment = analyzer.analyze(tweet['text'])
                results['sentiment_scores'].append(sentiment['compound'])
                
                # Categorize sentiment
                if sentiment['compound'] >= 0.05:
                    results['positive_tweets'] += 1
                elif sentiment['compound'] <= -0.05:
                    results['negative_tweets'] += 1
                else:
                    results['neutral_tweets'] += 1
                
                # Track top influencers
                user = tweet['user']
                results['top_influencers'].append({
                    'username': user['screen_name'],
                    'followers': user['followers_count'],
                    'tweet': tweet['text'][:100] + '...' if len(tweet['text']) > 100 else tweet['text'],
                    'sentiment': sentiment['compound']
                })
            
            # Calculate averages and metrics
            if results['sentiment_scores']:
                results['average_sentiment'] = sum(results['sentiment_scores']) / len(results['sentiment_scores'])
            
            # Sort influencers by follower count
            results['top_influencers'].sort(key=lambda x: x['followers'], reverse=True)
            results['top_influencers'] = results['top_influencers'][:10]  # Top 10
            
            # Get sample tweets
            results['tweet_samples'] = [{
                'text': t['text'][:200] + '...' if len(t['text']) > 200 else t['text'],
                'sentiment': s['compound'],
                'username': t['user']['screen_name']
            } for t, s in zip(tweets[:5], results['sentiment_scores'][:5])]  # First 5 tweets
            
            return results
            
        except Exception as e:
            logger.error(f"Error analyzing financial sentiment: {str(e)}")
            return {
                'ticker': ticker,
                'error': str(e)
            }
