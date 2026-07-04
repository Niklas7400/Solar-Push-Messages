import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _get_float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _get_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


@dataclass(frozen=True)
class NissanConfig:
    username: str
    password: str
    vin: Optional[str]
    ntfy_url: str
    ntfy_topic: str
    poll_interval_s: int
    charge_target_pct: float
    hysteresis_pct: float
    cooldown_minutes: int
    renotify_minutes: int


def load_nissan_config() -> NissanConfig:
    username = os.getenv("NISSAN_USERNAME")
    password = os.getenv("NISSAN_PASSWORD")
    if not username or not password:
        raise ValueError("NISSAN_USERNAME and NISSAN_PASSWORD are required")

    return NissanConfig(
        username=username,
        password=password,
        vin=os.getenv("NISSAN_VIN") or None,
        ntfy_url=os.getenv("NISSAN_NTFY_URL") or os.getenv("NTFY_URL", "https://ntfy.sh"),
        ntfy_topic=os.getenv("NISSAN_NTFY_TOPIC") or os.environ["NTFY_TOPIC"],
        poll_interval_s=_get_int("NISSAN_POLL_INTERVAL_SECONDS", 600),
        charge_target_pct=_get_float("NISSAN_CHARGE_TARGET_PCT", 80),
        hysteresis_pct=_get_float("NISSAN_HYSTERESIS_PCT", 2),
        cooldown_minutes=_get_int("NISSAN_COOLDOWN_MINUTES", 15),
        renotify_minutes=_get_int("NISSAN_RENOTIFY_MINUTES", 240),
    )
