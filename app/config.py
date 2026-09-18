"""Environment-only configuration. API credentials never go to the browser."""
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env', override=False)


def flag(key: str, default: str = 'false') -> bool:
    value = os.getenv(key, default).lower().strip()
    if value not in {'true', 'false', '1', '0'}:
        raise ValueError(f'{key} must be true/false')
    return value in {'true', '1'}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./data/dealer.db')
    environment: str = os.getenv('APP_ENV', 'local')
    timezone: str = os.getenv('APP_TIMEZONE', 'Asia/Shanghai')
    allowed_hosts: tuple = tuple(x.strip() for x in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',') if x.strip())
    cookie_secure: bool = flag('COOKIE_SECURE')
    session_hours: int = int(os.getenv('SESSION_HOURS', '8'))
    scheduler_enabled: bool = flag('SCHEDULER_ENABLED', 'true')
    report_hour: int = int(os.getenv('DAILY_REPORT_HOUR', '0'))
    report_minute: int = int(os.getenv('DAILY_REPORT_MINUTE', '15'))
    catchup_days: int = int(os.getenv('REPORT_CATCHUP_DAYS', '7'))
    allow_ai: bool = flag('ALLOW_AI_EXTERNAL')
    api_docs: bool = flag('API_DOCS_ENABLED', 'true')
    deepseek_key: str = os.getenv('DEEPSEEK_API_KEY', '')
    deepseek_url: str = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')
    deepseek_model: str = os.getenv('DEEPSEEK_MODEL', 'deepseek-flash')
    ai_timeout: int = int(os.getenv('DEEPSEEK_TIMEOUT_SECONDS', '60'))
    ai_max_records: int = int(os.getenv('AI_MAX_RECORDS', '400'))
    inventory_aging: int = int(os.getenv('INVENTORY_AGING_DAYS', '90'))
    repair_overdue: int = int(os.getenv('REPAIR_OVERDUE_DAYS', '7'))
    receivable_grace: int = int(os.getenv('RECEIVABLE_GRACE_DAYS', '3'))
    low_margin: float = float(os.getenv('LOW_GROSS_MARGIN_PERCENT', '2'))
    large_cash_yuan: int = int(os.getenv('LARGE_CASH_AMOUNT_YUAN', '50000'))
    discount_review: float = float(os.getenv('DISCOUNT_REVIEW_PERCENT', '15'))

    def __post_init__(self):
        ZoneInfo(self.timezone)
        if self.environment not in {'local', 'production', 'test'}:
            raise ValueError('APP_ENV must be local, production or test')
        if self.environment == 'production' and (not self.cookie_secure or '*' in self.allowed_hosts or 'testserver' in self.allowed_hosts):
            raise ValueError('Production requires COOKIE_SECURE=true and explicit ALLOWED_HOSTS (without testserver)')
        if not (0 <= self.report_hour <= 23 and 0 <= self.report_minute <= 59):
            raise ValueError('Invalid daily report time')
        if not (1 <= self.session_hours <= 48 and 1 <= self.catchup_days <= 31 and 1 <= self.ai_max_records <= 2000):
            raise ValueError('Invalid session/catchup/AI limit')
        if self.allow_ai and not self.deepseek_url.startswith('https://'):
            raise ValueError('External AI requests must use HTTPS')
        if min(self.inventory_aging, self.repair_overdue, self.receivable_grace, self.large_cash_yuan, self.ai_timeout) < 1:
            raise ValueError('Review thresholds and timeout must be positive')

settings = Settings()
