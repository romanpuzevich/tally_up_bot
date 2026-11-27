import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    token: str
    database_url: str
    timezone: ZoneInfo

    @classmethod
    def load(cls):
        load_dotenv()
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise SystemExit("Укажите BOT_TOKEN в .env или в переменных окружения.")
        return cls(token, os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/bot.db"),
                   ZoneInfo(os.getenv("APP_TIMEZONE", "Europe/Moscow")))
