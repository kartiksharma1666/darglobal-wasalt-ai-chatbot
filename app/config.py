import os

APP_NAME = "Property Intelligence Assistant"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "")
DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "/app/data/property_assistant.db"
)
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "12000"))
