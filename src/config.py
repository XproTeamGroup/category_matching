import os
from dotenv import load_dotenv

load_dotenv()

AI_BASE_URL: str = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
AI_API_KEY: str = os.getenv("AI_API_KEY", "")
AI_MODEL: str = os.getenv("AI_MODEL", "gpt-4")
BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "25"))
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
