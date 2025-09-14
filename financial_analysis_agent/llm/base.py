""
Base class for LLM clients.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union

class LLMClient(ABC):
    """Abstract base class for LLM clients."""
    
    @abstractmethod
    def generate(
        self, 
        prompt: str, 
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """Generate text from a prompt.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature (0-2)
            **kwargs: Additional model-specific parameters
            
        Returns:
            Generated text
        """
        pass
    
    @abstractmethod
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
            **kwargs: Additional model-specific parameters
            
        Returns:
            Generated response
        """
        pass
    
    @abstractmethod
    def embeddings(self, text: Union[str, List[str]], **kwargs) -> List[List[float]]:
        """Generate embeddings for text.
        
        Args:
            text: Input text or list of texts
            **kwargs: Additional model-specific parameters
            
        Returns:
            List of embeddings
        """
        pass
    
    @abstractmethod
    def get_available_models(self) -> List[str]:
        """Get list of available models.
        
        Returns:
            List of model names
        """
        pass
    
    def _format_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Format messages for the API.
        
        Args:
            messages: List of message dictionaries
            
        Returns:
            Formatted messages
        """
        formatted = []
        for msg in messages:
            role = msg.get('role', 'user').lower()
            content = msg.get('content', '').strip()
            if content:
                formatted.append({'role': role, 'content': content})
        return formatted
    
    def _validate_temperature(self, temperature: float) -> float:
        """Validate temperature parameter."""
        return max(0.0, min(2.0, float(temperature)))
    
    def _validate_max_tokens(self, max_tokens: int) -> int:
        """Validate max_tokens parameter."""
        return max(1, min(100000, int(max_tokens)))
