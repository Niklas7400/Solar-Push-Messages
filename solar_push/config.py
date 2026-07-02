import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get_float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _get_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    inverter_host: str
    inverter_port: int
    inverter_slave_id: int
    ntfy_url: str
    ntfy_topic: str
    poll_interval_s: int
    increase_threshold_w: float
    decrease_threshold_w: float
    hysteresis_w: float
    cooldown_minutes: int
    renotify_minutes: int
    grid_export_positive: bool


def load_config() -> Config:
    return Config(
        inverter_host=os.environ["INVERTER_HOST"],
        inverter_port=_get_int("INVERTER_PORT", 502),
        inverter_slave_id=_get_int("INVERTER_SLAVE_ID", 0),
        ntfy_url=os.getenv("NTFY_URL", "https://ntfy.sh"),
        ntfy_topic=os.environ["NTFY_TOPIC"],
        poll_interval_s=_get_int("POLL_INTERVAL_SECONDS", 60),
        increase_threshold_w=_get_float("INCREASE_THRESHOLD_W", 1000),
        decrease_threshold_w=_get_float("DECREASE_THRESHOLD_W", 1000),
        hysteresis_w=_get_float("HYSTERESIS_W", 200),
        cooldown_minutes=_get_int("COOLDOWN_MINUTES", 15),
        renotify_minutes=_get_int("RENOTIFY_MINUTES", 45),
        grid_export_positive=_get_bool("GRID_EXPORT_POSITIVE", True),
    )
