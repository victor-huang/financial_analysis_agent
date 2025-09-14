"""Reddit client for fetching and analyzing financial discussions."""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import praw
import pandas as pd
import pytz

from ..config import get_config

logger = logging.getLogger(__name__)

class RedditClient:
    """Client for interacting with Reddit API."""
    
    def __init__(self, 
                 client_id: str = None, 
                 client_secret: str = None, 
                 user_agent: str = None,
                 username: str = None,
                 password: str = None):
        """Initialize Reddit client with API credentials."""
        self.config = get_config()
        
        # Use provided credentials or fall back to config
        self.client_id = client_id or self.config.get('apis.reddit.client_id')
        self.client_secret = client_secret or self.config.get('apis.reddit.client_secret')
        self.user_agent = user_agent or self.config.get('apis.reddit.user_agent')
        self.username = username or self.config.get('apis.reddit.username')
        self.password = password or self.config.get('apis.reddit.password')
        
        self.reddit = None
        self.authenticate()
    
    def authenticate(self) -> bool:
        """Authenticate with Reddit API."""
        try:
            if not all([self.client_id, self.client_secret, self.user_agent]):
                logger.warning("Reddit API credentials not fully configured")
                return False
            
            # Create Reddit instance
            if self.username and self.password:
                # Script (read-write) auth
                self.reddit = praw.Reddit(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    user_agent=self.user_agent,
                    username=self.username,
                    password=self.password
                )
            else:
                # Read-only auth
                self.reddit = praw.Reddit(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    user_agent=self.user_agent
                )
            
            # Verify authentication
            if not self.reddit.read_only:
                logger.info("Successfully authenticated with Reddit API (read-write mode)")
            else:
                logger.info("Successfully authenticated with Reddit API (read-only mode)")
                
            return True
            
        except Exception as e:
            logger.error(f"Reddit authentication failed: {str(e)}")
            self.reddit = None
            return False
    
    def get_subreddit_posts(
        self, 
        subreddit_name: str, 
        limit: int = 25,
        time_filter: str = 'week',
        sort_by: str = 'hot'
    ) -> List[Dict]:
        """Get posts from a subreddit.
        
        Args:
            subreddit_name: Name of the subreddit (without r/)
            limit: Maximum number of posts to retrieve (1-1000)
            time_filter: Time period to filter by ('hour', 'day', 'week', 'month', 'year', 'all')
            sort_by: How to sort results ('hot', 'new', 'top', 'rising')
            
        Returns:
            List of post dictionaries
        """
        if not self.reddit:
            logger.error("Reddit client not authenticated")
            return []
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            
            # Get posts based on sort method
            if sort_by == 'hot':
                posts = subreddit.hot(limit=min(limit, 1000))
            elif sort_by == 'new':
                posts = subreddit.new(limit=min(limit, 1000))
            elif sort_by == 'top':
                posts = subreddit.top(time_filter=time_filter, limit=min(limit, 1000))
            elif sort_by == 'rising':
                posts = subreddit.rising(limit=min(limit, 100))
            else:
                raise ValueError(f"Invalid sort_by value: {sort_by}")
            
            # Process posts
            result = []
            for post in posts:
                try:
                    result.append(self._parse_post(post))
                except Exception as e:
                    logger.warning(f"Error parsing post {post.id}: {str(e)}")
                    continue
                
                if len(result) >= limit:
                    break
            
            logger.info(f"Retrieved {len(result)} posts from r/{subreddit_name}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting subreddit posts from r/{subreddit_name}: {str(e)}")
            return []
    
    def search_posts(
        self, 
        query: str, 
        subreddit: str = None,
        limit: int = 25,
        sort_by: str = 'relevance',
        time_filter: str = 'all',
        syntax: str = 'plain'
    ) -> List[Dict]:
        """Search for posts matching a query.
        
        Args:
            query: Search query string
            subreddit: Optional subreddit to search within
            limit: Maximum number of results to return (1-1000)
            sort_by: How to sort results ('relevance', 'hot', 'top', 'new', 'comments')
            time_filter: Time period to filter by ('all', 'day', 'hour', 'month', 'week', 'year')
            syntax: Search syntax ('cloudsearch', 'lucene', 'plain')
            
        Returns:
            List of post dictionaries
        """
        if not self.reddit:
            logger.error("Reddit client not authenticated")
            return []
        
        try:
            # Build search query
            search_query = query
            if subreddit:
                search_query = f'subreddit:{subreddit} {query}'
            
            # Execute search
            results = list(self.reddit.subreddit('all').search(
                query=search_query,
                sort=sort_by,
                time_filter=time_filter,
                syntax=syntax,
                limit=min(limit, 1000)
            ))
            
            # Process results
            posts = []
            for post in results:
                try:
                    posts.append(self._parse_post(post))
                except Exception as e:
                    logger.warning(f"Error parsing search result {post.id}: {str(e)}")
                    continue
                
                if len(posts) >= limit:
                    break
            
            logger.info(f"Found {len(posts)} posts matching query: {query}")
            return posts
            
        except Exception as e:
            logger.error(f"Error searching Reddit: {str(e)}")
            return []
    
    def get_post_comments(
        self, 
        post_id: str, 
        limit: int = 100,
        sort: str = 'top',
        max_depth: int = 5
    ) -> Dict[str, Any]:
        """Get comments for a specific post.
        
        Args:
            post_id: ID of the post (can be fullname or just the ID)
            limit: Maximum number of top-level comments to retrieve
            sort: How to sort comments ('confidence', 'top', 'new', 'controversial', 'old', 'random', 'qa', 'live'
            max_depth: Maximum depth of comment tree to traverse
            
        Returns:
            Dictionary with post details and comments
        """
        if not self.reddit:
            logger.error("Reddit client not authenticated")
            return {}
        
        try:
            # Ensure post_id is in the correct format
            if not post_id.startswith('t3_'):
                post_id = f't3_{post_id}'
            
            # Get the submission
            submission = self.reddit.submission(id=post_id.split('_')[-1])
            
            # Set the comment sort order
            if hasattr(submission, 'comment_sort'):
                submission.comment_sort = sort
            
            # Replace MoreComments objects with actual comments
            submission.comments.replace_more(limit=None)
            
            # Process comments recursively
            def process_comment(comment, depth=0):
                if depth > max_depth:
                    return None
                    
                result = {
                    'id': comment.id,
                    'author': comment.author.name if comment.author else '[deleted]',
                    'body': comment.body,
                    'score': comment.score,
                    'created_utc': datetime.utcfromtimestamp(comment.created_utc).isoformat(),
                    'depth': depth,
                    'replies': []
                }
                
                # Process replies
                if hasattr(comment, 'replies'):
                    for reply in comment.replies:
                        processed_reply = process_comment(reply, depth + 1)
                        if processed_reply:
                            result['replies'].append(processed_reply)
                
                return result
            
            # Get top-level comments
            comments = []
            for comment in submission.comments:
                processed_comment = process_comment(comment)
                if processed_comment:
                    comments.append(processed_comment)
                
                if len(comments) >= limit:
                    break
            
            # Prepare result
            result = {
                'post': self._parse_post(submission),
                'comments': comments,
                'comment_count': len(submission.comments.list())
            }
            
            logger.info(f"Retrieved {len(comments)} comments for post {post_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting comments for post {post_id}: {str(e)}")
            return {}
    
    def get_subreddit_info(self, subreddit_name: str) -> Dict:
        """Get information about a subreddit."""
        if not self.reddit:
            logger.error("Reddit client not authenticated")
            return {}
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            
            return {
                'name': subreddit.display_name,
                'title': subreddit.title,
                'description': subreddit.description,
                'public_description': subreddit.public_description,
                'subscribers': subreddit.subscribers,
                'active_users': subreddit.accounts_active,
                'created_utc': datetime.utcfromtimestamp(subreddit.created_utc).isoformat(),
                'over18': subreddit.over18,
                'submission_type': subreddit.submission_type,
                'spoilers_enabled': subreddit.spoilers_enabled,
                'wiki_enabled': subreddit.wiki_enabled
            }
            
        except Exception as e:
            logger.error(f"Error getting info for r/{subreddit_name}: {str(e)}")
            return {}
    
    def get_financial_sentiment(
        self, 
        ticker: str, 
        subreddits: List[str] = None,
        limit_per_sub: int = 50,
        days: int = 7
    ) -> Dict:
        """Analyze sentiment of Reddit posts about a financial instrument.
        
        Args:
            ticker: Stock/crypto ticker symbol
            subreddits: List of subreddits to search (default: common finance/investing subs)
            limit_per_sub: Maximum number of posts to analyze per subreddit
            days: Number of days to look back
            
        Returns:
            Dictionary with sentiment analysis results
        """
        try:
            if not subreddits:
                subreddits = [
                    'stocks', 'investing', 'wallstreetbets', 'stockmarket',
                    'pennystocks', 'smallstreetbets', 'options', 'daytrading'
                ]
            
            # Search for posts about the ticker
            query = f'${ticker} OR {ticker} stock OR {ticker} price OR {ticker} earnings'
            
            all_posts = []
            for subreddit in subreddits:
                try:
                    posts = self.search_posts(
                        query=query,
                        subreddit=subreddit,
                        limit=limit_per_sub,
                        time_filter='week',
                        sort_by='new'
                    )
                    all_posts.extend(posts)
                except Exception as e:
                    logger.warning(f"Error searching in r/{subreddit}: {str(e)}")
                    continue
            
            if not all_posts:
                return {
                    'ticker': ticker,
                    'post_count': 0,
                    'error': 'No posts found'
                }
            
            # Filter by date
            min_date = datetime.utcnow() - timedelta(days=days)
            recent_posts = [
                p for p in all_posts 
                if datetime.fromisoformat(p['created_utc']) >= min_date
            ]
            
            if not recent_posts:
                return {
                    'ticker': ticker,
                    'post_count': 0,
                    'error': f'No posts in the last {days} days'
                }
            
            # Analyze sentiment
            from .sentiment_analyzer import SentimentAnalyzer
            analyzer = SentimentAnalyzer()
            
            results = {
                'ticker': ticker,
                'post_count': len(recent_posts),
                'time_period': {
                    'start': min(p['created_utc'] for p in recent_posts),
                    'end': max(p['created_utc'] for p in recent_posts)
                },
                'subreddits': {},
                'sentiment_scores': [],
                'average_sentiment': 0.0,
                'positive_posts': 0,
                'neutral_posts': 0,
                'negative_posts': 0,
                'top_posts': [],
                'engagement_metrics': {
                    'total_comments': 0,
                    'total_score': 0,
                    'avg_comments_per_post': 0,
                    'avg_score_per_post': 0
                }
            }
            
            # Process each post
            for post in recent_posts:
                # Get sentiment
                text = f"{post['title']}. {post['selftext']}"
                sentiment = analyzer.analyze(text)
                
                # Store sentiment score
                results['sentiment_scores'].append(sentiment['compound'])
                
                # Categorize sentiment
                if sentiment['compound'] >= 0.05:
                    results['positive_posts'] += 1
                elif sentiment['compound'] <= -0.05:
                    results['negative_posts'] += 1
                else:
                    results['neutral_posts'] += 1
                
                # Update engagement metrics
                results['engagement_metrics']['total_comments'] += post['num_comments']
                results['engagement_metrics']['total_score'] += post['score']
                
                # Track by subreddit
                subreddit = post['subreddit']
                if subreddit not in results['subreddits']:
                    results['subreddits'][subreddit] = {
                        'post_count': 0,
                        'avg_sentiment': 0.0,
                        'sentiment_scores': []
                    }
                
                results['subreddits'][subreddit]['post_count'] += 1
                results['subreddits'][subreddit]['sentiment_scores'].append(sentiment['compound'])
                
                # Track top posts by engagement (score + comments)
                engagement = post['score'] + (post['num_comments'] * 2)  # Weight comments more
                results['top_posts'].append({
                    'title': post['title'],
                    'url': f"https://reddit.com{post['permalink']}",
                    'subreddit': post['subreddit'],
                    'score': post['score'],
                    'comments': post['num_comments'],
                    'engagement': engagement,
                    'sentiment': sentiment['compound'],
                    'created_utc': post['created_utc']
                })
            
            # Calculate averages and metrics
            if results['sentiment_scores']:
                results['average_sentiment'] = sum(results['sentiment_scores']) / len(results['sentiment_scores'])
                
                # Calculate subreddit average sentiments
                for subreddit, data in results['subreddits'].items():
                    if data['sentiment_scores']:
                        data['avg_sentiment'] = sum(data['sentiment_scores']) / len(data['sentiment_scores'])
                    del data['sentiment_scores']  # Clean up
            
            # Sort top posts by engagement
            results['top_posts'].sort(key=lambda x: x['engagement'], reverse=True)
            results['top_posts'] = results['top_posts'][:10]  # Top 10 posts
            
            # Calculate engagement metrics
            if results['post_count'] > 0:
                results['engagement_metrics']['avg_comments_per_post'] = (
                    results['engagement_metrics']['total_comments'] / results['post_count']
                )
                results['engagement_metrics']['avg_score_per_post'] = (
                    results['engagement_metrics']['total_score'] / results['post_count']
                )
            
            return results
            
        except Exception as e:
            logger.error(f"Error analyzing Reddit sentiment for {ticker}: {str(e)}")
            return {
                'ticker': ticker,
                'error': str(e)
            }
    
    def _parse_post(self, post) -> Dict:
        """Parse a Reddit post into a dictionary."""
        return {
            'id': post.id,
            'title': post.title,
            'author': post.author.name if post.author else '[deleted]',
            'score': post.score,
            'upvote_ratio': getattr(post, 'upvote_ratio', 0),
            'num_comments': getattr(post, 'num_comments', 0),
            'subreddit': post.subreddit.display_name,
            'subreddit_subscribers': getattr(post.subreddit, 'subscribers', 0),
            'url': f"https://reddit.com{post.permalink}",
            'selftext': getattr(post, 'selftext', ''),
            'is_self': getattr(post, 'is_self', False),
            'created_utc': datetime.utcfromtimestamp(post.created_utc).isoformat(),
            'over_18': getattr(post, 'over_18', False),
            'spoiler': getattr(post, 'spoiler', False),
            'stickied': getattr(post, 'stickied', False),
            'locked': getattr(post, 'locked', False),
            'distinguished': getattr(post, 'distinguished', None),
            'flair': getattr(post, 'link_flair_text', None),
            'domain': getattr(post, 'domain', ''),
            'url_overridden_by_dest': getattr(post, 'url_overridden_by_dest', ''),
            'thumbnail': getattr(post, 'thumbnail', ''),
            'preview': getattr(post, 'preview', {}).get('images', [{}])[0].get('source', {}).get('url', '') 
                       if hasattr(post, 'preview') and hasattr(post.preview, 'images') else ''
        }
