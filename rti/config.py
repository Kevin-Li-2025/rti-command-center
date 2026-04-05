from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings

_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # llm
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.1"

    # data sources
    newsapi_key: str = ""
    aviationstack_key: str = ""
    opensky_user: str = ""
    opensky_pass: str = ""

    # pipeline
    pipeline_interval_hours: int = 4
    escalation_threshold: int = 50  # layer-2 reasoning kicks in above this

    # storage
    cache_dir: Path = _ROOT / ".cache"
    db_path: Path = _ROOT / "rti.db"

    # server
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def active_model(self) -> str:
        if self.llm_provider == "deepseek":
            return self.deepseek_model
        if self.llm_provider == "ollama":
            return self.ollama_model
        return self.llm_model

    @property
    def fast_model(self) -> str:
        """cheapest model available — used for layer-1 structured extraction."""
        if self.llm_provider == "deepseek":
            return "deepseek-chat"
        if self.llm_provider == "ollama":
            return self.ollama_model
        return "gpt-4o-mini"

    @property
    def llm_base_url(self) -> str:
        if self.llm_provider == "deepseek":
            return "https://api.deepseek.com"
        if self.llm_provider == "ollama":
            return self.ollama_base_url
        return "https://api.openai.com/v1"

    @property
    def llm_api_key(self) -> str:
        if self.llm_provider == "deepseek":
            return self.deepseek_api_key
        if self.llm_provider == "ollama":
            return "ollama"
        return self.openai_api_key

    model_config = {
        "env_file": str(_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
