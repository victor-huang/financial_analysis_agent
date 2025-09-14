"""Sentiment analysis module using various NLP techniques and LLMs."""
import logging
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import torch
from scipy.special import softmax
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
from nltk.tokenize import sent_tokenize

from ..config import get_config

# Download required NLTK data
nltk.download('vader_lexicon', quiet=True)
nltk.download('punkt', quiet=True)

logger = logging.getLogger(__name__)

class SentimentAnalyzer:
    """Class for performing sentiment analysis on financial text."""
    
    def __init__(self, model_name: str = None, use_gpu: bool = False):
        """Initialize the sentiment analyzer.
        
        Args:
            model_name: Name of the pre-trained model to use
            use_gpu: Whether to use GPU if available
        """
        self.config = get_config()
        self.device = 0 if use_gpu and torch.cuda.is_available() else -1
        self.model_name = model_name or "ProsusAI/finbert"
        self.tokenizer = None
        self.model = None
        self.sia = SentimentIntensityAnalyzer()
        
        # Default sentiment labels
        self.labels = ["negative", "neutral", "positive"]
        
        # Initialize the model
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the sentiment analysis model."""
        try:
            # Load the tokenizer and model
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            
            # Move model to GPU if available
            if self.device == 0:
                self.model = self.model.cuda()
            
            logger.info(f"Initialized sentiment analyzer with model: {self.model_name}")
            
        except Exception as e:
            logger.error(f"Error initializing sentiment model: {str(e)}")
            logger.warning("Falling back to VADER sentiment analyzer")
            self.model = None
    
    def analyze(self, text: str, method: str = "auto") -> Dict[str, float]:
        """Analyze the sentiment of the input text.
        
        Args:
            text: Input text to analyze
            method: Analysis method ('auto', 'finbert', 'vader')
            
        Returns:
            Dictionary with sentiment scores
        """
        if not text or not isinstance(text, str) or not text.strip():
            return {"positive": 0.0, "negative": 0.0, "neutral": 1.0, "compound": 0.0}
        
        # Clean the text
        text = self._clean_text(text)
        
        # Choose analysis method
        if method == "auto":
            if self.model and len(text.split()) > 3:  # Use FinBERT for longer text
                return self._analyze_with_finbert(text)
            else:
                return self._analyze_with_vader(text)
        elif method == "finbert" and self.model:
            return self._analyze_with_finbert(text)
        else:
            return self._analyze_with_vader(text)
    
    def _analyze_with_finbert(self, text: str) -> Dict[str, float]:
        """Analyze sentiment using FinBERT model."""
        try:
            # Tokenize the text
            inputs = self.tokenizer(
                text, 
                return_tensors="pt", 
                padding=True, 
                truncation=True, 
                max_length=512
            )
            
            # Move inputs to the same device as the model
            if self.device == 0:
                inputs = {k: v.cuda() for k, v in inputs.items()}
            
            # Get model predictions
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            # Get predicted probabilities
            scores = torch.softmax(outputs.logits, dim=1).cpu().numpy()[0]
            
            # Map to output format
            result = {
                "positive": float(scores[2]),
                "negative": float(scores[0]),
                "neutral": float(scores[1]),
                "compound": float(scores[2] - scores[0])  # Range from -1 to 1
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error with FinBERT analysis: {str(e)}")
            # Fall back to VADER if FinBERT fails
            return self._analyze_with_vader(text)
    
    def _analyze_with_vader(self, text: str) -> Dict[str, float]:
        """Analyze sentiment using VADER sentiment analyzer."""
        try:
            # Get sentiment scores
            scores = self.sia.polarity_scores(text)
            
            # Map to the same format as FinBERT
            return {
                "positive": scores["pos"],
                "negative": scores["neg"],
                "neutral": scores["neu"],
                "compound": scores["compound"]
            }
            
        except Exception as e:
            logger.error(f"Error with VADER analysis: {str(e)}")
            # Return neutral if all else fails
            return {"positive": 0.0, "negative": 0.0, "neutral": 1.0, "compound": 0.0}
    
    def analyze_batch(self, texts: List[str], method: str = "auto") -> List[Dict[str, float]]:
        """Analyze sentiment for a batch of texts.
        
        Args:
            texts: List of input texts to analyze
            method: Analysis method ('auto', 'finbert', 'vader')
            
        Returns:
            List of sentiment analysis results
        """
        if not texts:
            return []
        
        # Clean all texts
        cleaned_texts = [self._clean_text(text) for text in texts if text and isinstance(text, str)]
        
        if method == "finbert" and self.model:
            return self._analyze_batch_with_finbert(cleaned_texts)
        else:
            return [self.analyze(text, method=method) for text in cleaned_texts]
    
    def _analyze_batch_with_finbert(self, texts: List[str]) -> List[Dict[str, float]]:
        """Analyze a batch of texts using FinBERT."""
        try:
            # Tokenize all texts
            inputs = self.tokenizer(
                texts, 
                return_tensors="pt", 
                padding=True, 
                truncation=True, 
                max_length=512
            )
            
            # Move inputs to the same device as the model
            if self.device == 0:
                inputs = {k: v.cuda() for k, v in inputs.items()}
            
            # Get model predictions
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            # Get predicted probabilities
            scores = torch.softmax(outputs.logits, dim=1).cpu().numpy()
            
            # Convert to list of result dictionaries
            results = []
            for score in scores:
                results.append({
                    "positive": float(score[2]),
                    "negative": float(score[0]),
                    "neutral": float(score[1]),
                    "compound": float(score[2] - score[0])
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Error with batch FinBERT analysis: {str(e)}")
            # Fall back to sequential VADER analysis
            return [self._analyze_with_vader(text) for text in texts]
    
    def get_sentiment_label(self, scores: Dict[str, float], threshold: float = 0.1) -> str:
        """Convert sentiment scores to a label.
        
        Args:
            scores: Dictionary with 'positive', 'negative', 'neutral' scores
            threshold: Threshold for considering a sentiment strong enough
            
        Returns:
            Sentiment label ('positive', 'negative', or 'neutral')
        """
        compound = scores.get("compound", 0)
        
        if compound >= threshold:
            return "positive"
        elif compound <= -threshold:
            return "negative"
        else:
            return "neutral"
    
    def analyze_sentiment_over_time(
        self, 
        texts: List[str], 
        timestamps: List[str],
        time_window: str = "1D"
    ) -> Dict[str, List[Dict]]:
        """Analyze sentiment over time.
        
        Args:
            texts: List of texts to analyze
            timestamps: List of corresponding timestamps (ISO format)
            time_window: Time window for grouping ('1D' for daily, '1W' for weekly, etc.)
            
        Returns:
            Dictionary with sentiment analysis results grouped by time window
        """
        if not texts or not timestamps or len(texts) != len(timestamps):
            return {}
        
        try:
            import pandas as pd
            
            # Create a DataFrame with texts and timestamps
            df = pd.DataFrame({
                'text': texts,
                'timestamp': pd.to_datetime(timestamps)
            })
            
            # Set timestamp as index and sort
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            
            # Analyze sentiment for each text
            df['sentiment'] = df['text'].apply(lambda x: self.analyze(x)['compound'])
            
            # Resample by time window and calculate statistics
            resampled = df['sentiment'].resample(time_window).agg(
                ['mean', 'count', 'std', 'min', 'max']
            )
            
            # Convert to list of dictionaries
            results = []
            for idx, row in resampled.iterrows():
                if row['count'] > 0:  # Only include non-empty windows
                    results.append({
                        'timestamp': idx.isoformat(),
                        'mean_sentiment': float(row['mean']),
                        'count': int(row['count']),
                        'std_dev': float(row['std']) if not pd.isna(row['std']) else 0.0,
                        'min_sentiment': float(row['min']),
                        'max_sentiment': float(row['max'])
                    })
            
            return {
                'time_series': results,
                'overall_sentiment': float(df['sentiment'].mean()),
                'total_samples': len(df)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment over time: {str(e)}")
            return {}
    
    def analyze_aspect_based_sentiment(
        self, 
        text: str, 
        aspects: List[str] = None,
        context_window: int = 3
    ) -> Dict[str, Dict[str, float]]:
        """Perform aspect-based sentiment analysis.
        
        Args:
            text: Input text to analyze
            aspects: List of aspects to analyze (if None, will try to extract them)
            context_window: Number of sentences to include as context around each mention
            
        Returns:
            Dictionary mapping aspects to their sentiment analysis
        """
        try:
            # If no aspects provided, try to extract them
            if not aspects:
                aspects = self._extract_aspects(text)
            
            # If still no aspects, return empty result
            if not aspects:
                return {}
            
            # Split text into sentences
            sentences = sent_tokenize(text)
            aspect_sentences = {aspect: [] for aspect in aspects}
            
            # Find sentences containing each aspect
            for i, sentence in enumerate(sentences):
                for aspect in aspects:
                    if aspect.lower() in sentence.lower():
                        # Get context window around the sentence
                        start = max(0, i - context_window)
                        end = min(len(sentences), i + context_window + 1)
                        context = ' '.join(sentences[start:end])
                        aspect_sentences[aspect].append(context)
            
            # Analyze sentiment for each aspect
            results = {}
            for aspect, contexts in aspect_sentences.items():
                if not contexts:
                    continue
                    
                # Analyze each context and average the results
                sentiments = [self.analyze(context) for context in contexts]
                avg_sentiment = {
                    'positive': sum(s['positive'] for s in sentiments) / len(sentiments),
                    'negative': sum(s['negative'] for s in sentiments) / len(sentiments),
                    'neutral': sum(s['neutral'] for s in sentiments) / len(sentiments),
                    'compound': sum(s['compound'] for s in sentiments) / len(sentiments),
                    'mentions': len(contexts)
                }
                results[aspect] = avg_sentiment
            
            return results
            
        except Exception as e:
            logger.error(f"Error in aspect-based sentiment analysis: {str(e)}")
            return {}
    
    def _extract_aspects(self, text: str, top_n: int = 5) -> List[str]:
        """Extract key aspects (topics) from text."""
        try:
            # Simple implementation using noun phrases
            # For production, consider using NER or topic modeling
            import spacy
            
            # Load English language model
            nlp = spacy.load("en_core_web_sm")
            doc = nlp(text)
            
            # Extract noun chunks and proper nouns
            aspects = set()
            
            # Add noun chunks
            for chunk in doc.noun_chunks:
                if len(chunk.text.split()) <= 3:  # Limit phrase length
                    aspects.add(chunk.text.lower())
            
            # Add proper nouns
            for ent in doc.ents:
                if ent.label_ in ["ORG", "PRODUCT", "GPE", "EVENT"]:
                    aspects.add(ent.text.lower())
            
            # Filter out common words
            common_words = {"company", "stock", "price", "market", "share", "shares", 
                          "day", "time", "year", "people", "thing", "something"}
            aspects = [a for a in aspects if a.lower() not in common_words]
            
            # Return top N aspects by frequency
            if len(aspects) > top_n:
                # Simple frequency-based selection
                from collections import Counter
                word_freq = Counter(" ".join(aspects).split())
                aspects = sorted(aspects, key=lambda x: sum(word_freq[w] for w in x.split()), reverse=True)
                aspects = aspects[:top_n]
            
            return aspects
            
        except Exception as e:
            logger.warning(f"Error extracting aspects: {str(e)}")
            # Fallback to simple word-based approach
            words = [w.lower() for w in text.split() if w.isalpha() and len(w) > 3]
            return list(set(words))[:top_n] if words else []
    
    def _clean_text(self, text: str) -> str:
        """Clean and preprocess text for sentiment analysis."""
        if not text:
            return ""
        
        # Basic cleaning
        text = text.strip()
        
        # Remove URLs
        import re
        text = re.sub(r'https?://\S+|www\.\S+', '', text)
        
        # Remove special characters and numbers
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
