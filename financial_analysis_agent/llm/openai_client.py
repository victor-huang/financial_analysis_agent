"""OpenAI API client for financial analysis."""
import os
import logging
from typing import Dict, List, Optional, Any, Union
import openai
from openai import OpenAI

from .base import LLMClient
from ..config import get_config

logger = logging.getLogger(__name__)

class OpenAIClient(LLMClient):
    """Client for interacting with OpenAI's API."""
    
    def __init__(self, api_key: str = None, model: str = None):
        """Initialize the OpenAI client.
        
        Args:
            api_key: OpenAI API key. If not provided, will try to get from config.
            model: Default model to use. If not provided, will use config or default.
        """
        self.config = get_config()
        self.api_key = api_key or self.config.get('apis.openai.api_key') or os.getenv('OPENAI_API_KEY')
        self.default_model = model or self.config.get('apis.openai.model', 'gpt-4')
        
        if not self.api_key:
            logger.warning("OpenAI API key not provided. Some functionality may be limited.")
        
        # Initialize the OpenAI client
        self.client = OpenAI(api_key=self.api_key)
    
    def generate(
        self, 
        prompt: str, 
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """Generate text from a prompt using the chat completion API.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature (0-2)
            **kwargs: Additional parameters for the API call
            
        Returns:
            Generated text
        """
        try:
            messages = [{"role": "user", "content": prompt}]
            return self.chat(messages, max_tokens, temperature, **kwargs)
        except Exception as e:
            logger.error(f"Error in OpenAI text generation: {str(e)}")
            raise
    
    def chat(
        self, 
        messages: List[Dict[str, str]],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """Generate chat completion.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature (0-2)
            **kwargs: Additional parameters for the API call
            
        Returns:
            Generated response
        """
        try:
            # Validate parameters
            temperature = self._validate_temperature(temperature)
            max_tokens = self._validate_max_tokens(max_tokens)
            
            # Format messages
            formatted_messages = self._format_messages(messages)
            
            # Prepare API parameters
            params = {
                "model": kwargs.pop('model', self.default_model),
                "messages": formatted_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                **kwargs
            }
            
            # Make the API call
            response = self.client.chat.completions.create(**params)
            
            # Extract and return the generated text
            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content.strip()
            
            return ""
            
        except Exception as e:
            logger.error(f"Error in OpenAI chat completion: {str(e)}")
            raise
    
    def embeddings(self, text: Union[str, List[str]], **kwargs) -> List[List[float]]:
        """Generate embeddings for text.
        
        Args:
            text: Input text or list of texts
            **kwargs: Additional parameters for the API call
            
        Returns:
            List of embeddings
        """
        try:
            # Handle single string input
            if isinstance(text, str):
                text = [text]
            
            # Prepare API parameters
            model = kwargs.pop('model', 'text-embedding-ada-002')
            
            # Make the API call
            response = self.client.embeddings.create(
                input=text,
                model=model,
                **kwargs
            )
            
            # Extract and return the embeddings
            return [item.embedding for item in response.data]
            
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise
    
    def get_available_models(self) -> List[str]:
        """Get list of available models.
        
        Returns:
            List of model names
        """
        try:
            response = self.client.models.list()
            return [model.id for model in response.data]
        except Exception as e:
            logger.error(f"Error retrieving available models: {str(e)}")
            return []
    
    def analyze_sentiment(
        self, 
        text: str, 
        model: str = None,
        **kwargs
    ) -> Dict[str, float]:
        """Analyze sentiment of the input text.
        
        Args:
            text: Input text to analyze
            model: Model to use for analysis
            **kwargs: Additional parameters for the API call
            
        Returns:
            Dictionary with sentiment scores
        """
        try:
            prompt = """
            Analyze the sentiment of the following financial text. 
            Return a JSON object with the following structure:
            {
                "sentiment": "positive", "negative", or "neutral",
                "confidence": float between 0 and 1,
                "explanation": "Brief explanation of the sentiment analysis"
            }
            
            Text to analyze:
            """ + text
            
            response = self.chat(
                [{"role": "user", "content": prompt}],
                model=model or self.default_model,
                **kwargs
            )
            
            # Parse the JSON response
            import json
            return json.loads(response.strip())
            
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {str(e)}")
            return {
                "sentiment": "error",
                "confidence": 0.0,
                "explanation": f"Error analyzing sentiment: {str(e)}"
            }
    
    def extract_financial_entities(
        self, 
        text: str, 
        entity_types: List[str] = None,
        model: str = None,
        **kwargs
    ) -> Dict[str, List[Dict]]:
        """Extract financial entities from text.
        
        Args:
            text: Input text to analyze
            entity_types: List of entity types to extract (e.g., ["company", "ticker", "financial_metric"])
            model: Model to use for extraction
            **kwargs: Additional parameters for the API call
            
        Returns:
            Dictionary mapping entity types to lists of entities
        """
        try:
            if not entity_types:
                entity_types = ["company", "ticker", "financial_metric", "currency", "percentage"]
            
            entity_types_str = ", ".join(f'"{et}"' for et in entity_types)
            
            prompt = f"""
            Extract financial entities from the following text. 
            Look for entities of these types: {entity_types_str}.
            
            Return a JSON object with entity types as keys and lists of entities as values.
            For each entity, include the text and the position in the original text.
            
            Example output:
            {{
                "company": [{{"text": "Apple", "start": 10, "end": 15}}],
                "ticker": [{{"text": "AAPL", "start": 20, "end": 24}}]
            }}
            
            Text to analyze:
            {text}
            """
            
            response = self.chat(
                [{"role": "user", "content": prompt}],
                model=model or self.default_model,
                **kwargs
            )
            
            # Parse the JSON response
            import json
            return json.loads(response.strip())
            
        except Exception as e:
            logger.error(f"Error extracting financial entities: {str(e)}")
            return {"error": f"Error extracting financial entities: {str(e)}"}
    
    def generate_financial_summary(
        self, 
        data: Dict[str, Any],
        analysis_type: str = "quarterly_earnings",
        model: str = None,
        **kwargs
    ) -> str:
        """Generate a financial summary from structured data.
        
        Args:
            data: Structured financial data
            analysis_type: Type of analysis to perform
            model: Model to use for generation
            **kwargs: Additional parameters for the API call
            
        Returns:
            Generated financial summary
        """
        try:
            # Convert data to string representation
            import json
            data_str = json.dumps(data, indent=2)
            
            prompt = f"""
            Generate a professional financial {analysis_type} summary based on the following data.
            Focus on key metrics, trends, and insights that would be valuable for investors.
            
            Data:
            {data_str}
            
            Summary:
            """
            
            return self.chat(
                [{"role": "user", "content": prompt}],
                model=model or self.default_model,
                **kwargs
            )
            
        except Exception as e:
            logger.error(f"Error generating financial summary: {str(e)}")
            return f"Error generating financial summary: {str(e)}"
