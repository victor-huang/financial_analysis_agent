"""Configuration management for the Financial Analysis Agent.
Handles environment variables and application settings."""

import os
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import yaml


class Config:
    """Central configuration class for the application."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Load environment variables from .env file if it exists
        load_dotenv()

        # Default configuration
        self._config = {
            "app": {
                "name": "financial_analysis_agent",
                "version": "0.1.0",
                "environment": os.getenv("ENVIRONMENT", "development"),
                "log_level": os.getenv("LOG_LEVEL", "INFO"),
            },
            "database": {
                "duckdb_path": os.getenv("DUCKDB_PATH", "./data/financial.duckdb")
            },
            "paths": {
                "data": os.getenv(
                    "DATA_DIR", str(Path(__file__).parent.parent / "data")
                ),
                "cache": os.getenv(
                    "CACHE_DIR", str(Path(__file__).parent.parent / ".cache")
                ),
            },
            "apis": {
                "alpha_vantage": {
                    "api_key": os.getenv("ALPHA_VANTAGE_API_KEY"),
                    "base_url": "https://www.alphavantage.co/query",
                },
                "openai": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": os.getenv("OPENAI_MODEL", "gpt-4"),
                },
                "twitter": {
                    "api_key": os.getenv("TWITTER_API_KEY"),
                    "api_secret": os.getenv("TWITTER_API_SECRET"),
                    "access_token": os.getenv("TWITTER_ACCESS_TOKEN"),
                    "access_token_secret": os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
                },
                "reddit": {
                    "client_id": os.getenv("REDDIT_CLIENT_ID"),
                    "client_secret": os.getenv("REDDIT_CLIENT_SECRET"),
                    "user_agent": os.getenv(
                        "REDDIT_USER_AGENT", "FinancialAnalysisAgent/0.1"
                    ),
                    "username": os.getenv("REDDIT_USERNAME"),
                    "password": os.getenv("REDDIT_PASSWORD"),
                },
                "finnhub": {
                    "api_key": os.getenv("FINNHUB_API_KEY"),
                    "base_url": "https://finnhub.io/api/v1",
                },
            },
        }

        # Create necessary directories
        self._create_directories()
        self._initialized = True

    def _create_directories(self):
        """Create necessary directories if they don't exist."""
        for path in self._config["paths"].values():
            os.makedirs(path, exist_ok=True)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot notation key."""
        keys = key.split(".")
        value = self._config

        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def to_dict(self) -> Dict[str, Any]:
        """Return the entire configuration as a dictionary."""
        return self._config

    def save_to_yaml(self, filepath: str = None):
        """Save configuration to a YAML file."""
        if filepath is None:
            filepath = os.path.join(self.get("paths.data"), "config.yaml")

        with open(filepath, "w") as f:
            yaml.safe_dump(self._config, f, default_flow_style=False)


# Global configuration instance
config = Config()


def get_config() -> Config:
    """Get the global configuration instance."""
    return config
