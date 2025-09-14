"""HuggingFace client for local model inference."""
import os
import logging
from typing import Dict, List, Optional, Any, Union
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    pipeline,
    StoppingCriteria,
    StoppingCriteriaList
)

from .base import LLMClient
from ..config import get_config

logger = logging.getLogger(__name__)

class StopOnTokens(StoppingCriteria):
    """Stop generation when certain tokens are generated."""
    def __init__(self, stop_token_ids):
        self.stop_token_ids = stop_token_ids

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs) -> bool:
        for stop_id in self.stop_token_ids:
            if input_ids[0][-1] == stop_id:
                return True
        return False

class HuggingFaceClient(LLMClient):
    """Client for local HuggingFace models."""
    
    def __init__(
        self, 
        model_name: str = None,
        model_path: str = None,
        device: str = None,
        **kwargs
    ):
        """Initialize the HuggingFace client.
        
        Args:
            model_name: Name of the model to load from HuggingFace Hub
            model_path: Local path to the model
            device: Device to run the model on ('cuda', 'mps', 'cpu')
            **kwargs: Additional model parameters
        """
        self.config = get_config()
        self.model_name = model_name or self.config.get('llm.hf_model_name', 'gpt2')
        self.model_path = model_path
        self.device = device or self._get_device()
        self.model = None
        self.tokenizer = None
        self.pipeline = None
        self.model_type = None
        self.stop_token_ids = None
        
        # Load model and tokenizer
        self._load_model(**kwargs)
    
    def _get_device(self) -> str:
        """Determine the best available device."""
        if torch.cuda.is_available():
            return 'cuda'
        elif torch.backends.mps.is_available():
            return 'mps'
        return 'cpu'
    
    def _load_model(self, **kwargs):
        """Load the model and tokenizer."""
        try:
            logger.info(f"Loading model: {self.model_name} on {self.device}")
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path or self.model_name,
                **kwargs
            )
            
            # Set padding token if not set
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # Determine model type
            model_config = self.tokenizer.pretrained_config
            is_encoder_decoder = getattr(model_config, "is_encoder_decoder", False)
            
            # Load appropriate model class
            if is_encoder_decoder:
                model_class = AutoModelForSeq2SeqLM
                self.model_type = "seq2seq"
            else:
                model_class = AutoModelForCausalLM
                self.model_type = "causal"
            
            # Load model
            self.model = model_class.from_pretrained(
                self.model_path or self.model_name,
                **kwargs
            ).to(self.device)
            
            # Set model to evaluation mode
            self.model.eval()
            
            # Initialize pipeline for text generation
            self.pipeline = pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer,
                device=0 if self.device == 'cuda' else -1,
                **kwargs
            )
            
            # Set stop token IDs if available
            if hasattr(self.tokenizer, 'eos_token_id') and self.tokenizer.eos_token_id is not None:
                self.stop_token_ids = [self.tokenizer.eos_token_id]
            
            logger.info(f"Successfully loaded model: {self.model_name}")
            
        except Exception as e:
            logger.error(f"Error loading model {self.model_name}: {str(e)}")
            raise
    
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
            **kwargs: Additional generation parameters
            
        Returns:
            Generated text
        """
        try:
            # Validate parameters
            temperature = self._validate_temperature(temperature)
            max_tokens = self._validate_max_tokens(max_tokens)
            
            # Prepare generation parameters
            gen_kwargs = {
                "max_length": len(self.tokenizer.encode(prompt)) + max_tokens,
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "do_sample": temperature > 0,
                "pad_token_id": self.tokenizer.eos_token_id,
                **kwargs
            }
            
            # Add stopping criteria if available
            if self.stop_token_ids:
                stop_criteria = StopOnTokens(self.stop_token_ids)
                gen_kwargs["stopping_criteria"] = StoppingCriteriaList([stop_criteria])
            
            # Generate text
            if self.model_type == "causal":
                # For causal LMs, we can use the pipeline
                outputs = self.pipeline(
                    prompt,
                    max_length=gen_kwargs["max_length"],
                    temperature=gen_kwargs["temperature"],
                    do_sample=gen_kwargs["do_sample"],
                    pad_token_id=gen_kwargs["pad_token_id"],
                    **{k: v for k, v in gen_kwargs.items() if k not in ["max_length", "temperature", "do_sample", "pad_token_id"]}
                )
                
                # Extract the generated text
                if isinstance(outputs, list) and len(outputs) > 0:
                    generated_text = outputs[0]["generated_text"]
                    # Remove the input prompt from the output
                    if generated_text.startswith(prompt):
                        generated_text = generated_text[len(prompt):].strip()
                    return generated_text
                
                return ""
                
            else:
                # For encoder-decoder models, we need to handle them differently
                inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
                
                with torch.no_grad():
                    outputs = self.model.generate(
                        **inputs,
                        max_length=gen_kwargs["max_length"],
                        temperature=gen_kwargs["temperature"],
                        do_sample=gen_kwargs["do_sample"],
                        pad_token_id=gen_kwargs["pad_token_id"],
                        **{k: v for k, v in gen_kwargs.items() if k not in ["max_length", "temperature", "do_sample", "pad_token_id"]}
                    )
                
                # Decode the generated tokens
                generated_text = self.tokenizer.decode(
                    outputs[0], 
                    skip_special_tokens=True
                )
                
                # Remove the input prompt from the output
                if generated_text.startswith(prompt):
                    generated_text = generated_text[len(prompt):].strip()
                
                return generated_text
                
        except Exception as e:
            logger.error(f"Error in text generation: {str(e)}")
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
            **kwargs: Additional generation parameters
            
        Returns:
            Generated response
        """
        try:
            # Format messages into a single prompt
            prompt = self._format_chat_prompt(messages)
            
            # Generate response
            return self.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            
        except Exception as e:
            logger.error(f"Error in chat completion: {str(e)}")
            raise
    
    def _format_chat_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Format chat messages into a single prompt.
        
        This is a simple implementation that can be overridden by subclasses
        to handle different chat formats.
        """
        prompt = ""
        
        for message in messages:
            role = message.get('role', 'user').lower()
            content = message.get('content', '').strip()
            
            if not content:
                continue
                
            if role == 'system':
                prompt += f"System: {content}\n\n"
            elif role == 'assistant':
                prompt += f"Assistant: {content}\n\n"
            elif role == 'user':
                prompt += f"User: {content}\n\n"
            else:
                prompt += f"{role.capitalize()}: {content}\n\n"
        
        # Add assistant prefix for the model to start generating
        prompt += "Assistant:"
        return prompt
    
    def embeddings(self, text: Union[str, List[str]], **kwargs) -> List[List[float]]:
        """Generate embeddings for text.
        
        Args:
            text: Input text or list of texts
            **kwargs: Additional parameters for the model
            
        Returns:
            List of embeddings
        """
        try:
            # Handle single string input
            if isinstance(text, str):
                text = [text]
            
            # Tokenize input
            inputs = self.tokenizer(
                text, 
                padding=True, 
                truncation=True, 
                return_tensors="pt"
            ).to(self.device)
            
            # Generate embeddings
            with torch.no_grad():
                outputs = self.model(**inputs, output_hidden_states=True)
                
                # Use the last hidden state as embeddings
                # For BERT-style models, this is the [CLS] token
                # For GPT-style models, we can use the last token's hidden state
                if hasattr(outputs, 'last_hidden_state'):
                    embeddings = outputs.last_hidden_state
                elif hasattr(outputs, 'hidden_states') and len(outputs.hidden_states) > 0:
                    # Use the last layer's hidden state
                    embeddings = outputs.hidden_states[-1]
                else:
                    raise ValueError("Could not extract embeddings from model output")
                
                # Get the [CLS] token embedding or mean pooling
                if self.model_type == 'seq2seq':
                    # For encoder-decoder models, use the encoder's last hidden state
                    if hasattr(outputs, 'encoder_last_hidden_state'):
                        embeddings = outputs.encoder_last_hidden_state
                    pooled = embeddings.mean(dim=1)  # Mean pooling
                else:
                    # For causal LMs, use the last token's hidden state
                    pooled = embeddings[:, -1, :]
            
            # Convert to CPU and return as list of lists
            return pooled.cpu().numpy().tolist()
            
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise
    
    def get_available_models(self) -> List[str]:
        """Get list of available models.
        
        This is a placeholder. In a real implementation, you might want to
        return a list of supported models or check the local model directory.
        """
        return [self.model_name] if self.model_name else []
    
    def analyze_sentiment(
        self, 
        text: str, 
        model_name: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Analyze sentiment of the input text.
        
        Args:
            text: Input text to analyze
            model_name: Optional specific model to use
            **kwargs: Additional parameters for the analysis
            
        Returns:
            Dictionary with sentiment analysis results
        """
        try:
            # If a specific sentiment analysis model is provided, use it
            if model_name and model_name != self.model_name:
                from transformers import pipeline
                sentiment_pipeline = pipeline(
                    "sentiment-analysis",
                    model=model_name,
                    device=0 if self.device == 'cuda' else -1
                )
                result = sentiment_pipeline(text, **kwargs)[0]
                return {
                    'sentiment': result['label'].lower(),
                    'confidence': float(result['score']),
                    'explanation': f"Predicted as {result['label']} with confidence {result['score']:.2f}"
                }
            
            # Otherwise, use the current model with a prompt
            prompt = f"""
            Analyze the sentiment of the following text. 
            Respond with a single word: 'positive', 'negative', or 'neutral'.
            
            Text: "{text}"
            
            Sentiment:
            """
            
            response = self.generate(
                prompt=prompt,
                max_tokens=10,
                temperature=0.1,
                **kwargs
            ).strip().lower()
            
            # Parse the response
            if 'positive' in response:
                sentiment = 'positive'
            elif 'negative' in response:
                sentiment = 'negative'
            else:
                sentiment = 'neutral'
            
            return {
                'sentiment': sentiment,
                'confidence': 0.8,  # Placeholder
                'explanation': f"Predicted as {sentiment} based on model analysis"
            }
            
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {str(e)}")
            return {
                'sentiment': 'error',
                'confidence': 0.0,
                'explanation': f"Error analyzing sentiment: {str(e)}"
            }
    
    def extract_financial_entities(
        self, 
        text: str, 
        entity_types: List[str] = None,
        **kwargs
    ) -> Dict[str, List[Dict]]:
        """Extract financial entities from text.
        
        Args:
            text: Input text to analyze
            entity_types: List of entity types to extract
            **kwargs: Additional parameters for the extraction
            
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
            
            response = self.generate(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.1,
                **kwargs
            )
            
            # Try to parse the JSON response
            import json
            try:
                return json.loads(response.strip())
            except json.JSONDecodeError:
                # If JSON parsing fails, try to extract just the JSON part
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
                return {"error": "Could not parse entity extraction response"}
            
        except Exception as e:
            logger.error(f"Error extracting financial entities: {str(e)}")
            return {"error": f"Error extracting financial entities: {str(e)}"}
    
    def generate_financial_summary(
        self, 
        data: Dict[str, Any],
        analysis_type: str = "quarterly_earnings",
        **kwargs
    ) -> str:
        """Generate a financial summary from structured data.
        
        Args:
            data: Structured financial data
            analysis_type: Type of analysis to perform
            **kwargs: Additional parameters for generation
            
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
            
            return self.generate(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.5,
                **kwargs
            )
            
        except Exception as e:
            logger.error(f"Error generating financial summary: {str(e)}")
            return f"Error generating financial summary: {str(e)}"
