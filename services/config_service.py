from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional, List
import os
import json
from pathlib import Path

class DatabaseSettings(BaseSettings):
    driver: str = Field(default="ODBC Driver 17 for SQL Server", alias="DB_DRIVER")
    server: Optional[str] = None
    database: Optional[str] = None
    uid: Optional[str] = None
    pwd: Optional[str] = None
    timeout: int = 15
    trust_server_certificate: bool = False
    encrypt: bool = True
    port: Optional[int] = 1433
    configured: bool = False

    def update_fields(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.configured = True

class LLMSettings(BaseSettings):
    model_path: Optional[str] = Field(default=None, alias="MODEL_PATH")
    n_gpu_layers: int = Field(default=0, alias="MODEL_GPU_LAYERS")
    n_ctx: int = Field(default=8096, alias="MODEL_CTX")
    n_threads: int = Field(default=8, alias="MODEL_THREADS")

class FAISSSettings(BaseSettings):
    index_path: str = Field(default="schema.index", alias="FAISS_INDEX_PATH")
    strings_path: str = Field(default="schema_strings.npy", alias="FAISS_STRINGS_PATH")
    retrieval_k: int = Field(default=7, alias="FAISS_K")

class GeminiSettings(BaseSettings):
    api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    base_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta/models", alias="GEMINI_BASE_API_URL")
    model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL_FOR_SQL")

class AppSettings(BaseSettings):
    env: str = Field(default="development", alias="FLASK_ENV")
    inference: str = "gemini"
    inference_mode_ui: Optional[str] = None
    auto_log_learning: bool = True
    auto_summarize: bool = False
    chat_session_limit: int = 5
    pii_masking: bool = True
    audit_logging: bool = True
    data_retention: int = 90
    temperature: float = 0.1
    learning_rate: float = 0.3
    secret_key: str = Field(default="dev-secret-key", alias="SECRET_KEY")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    db: DatabaseSettings = DatabaseSettings()
    llm: LLMSettings = LLMSettings()
    faiss: FAISSSettings = FAISSSettings()
    gemini: GeminiSettings = GeminiSettings()
    app: AppSettings = AppSettings()
    selection: List[str] = []

    @classmethod
    def load(cls, path: Path) -> "Settings":
        if not path.exists():
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return cls(**data)
        except Exception:
            return cls()

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))

settings = Settings()
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "data" / "asklytics_config.json"

def get_settings() -> Settings:
    global settings
    if not hasattr(get_settings, "_loaded"):
        settings = Settings.load(CONFIG_PATH)
        get_settings._loaded = True
    return settings

def save_settings(new_settings: Settings):
    global settings
    settings = new_settings
    settings.save(CONFIG_PATH)
