from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Infrastructure (existing)
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@db:5432/infodemic"
    LOCAL_STORAGE_ROOT: str = "/app/storage"

    # Transcription
    WHISPER_PROVIDER: str = "faster_whisper"   # "faster_whisper" | "openai"
    WHISPER_MODEL: str = "base"                 # "tiny" | "base" | "small" | "medium" | "large-v3"

    # Inference
    INFERENCE_PROVIDER: str = "openai"          # "openai" | "anthropic" | "ollama"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-opus-4-6"
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "mistral"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
