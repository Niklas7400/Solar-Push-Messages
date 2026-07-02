import os
from dataclasses import dataclass
from typing import Optional

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
    data_source: str  # "modbus" or "cloud"
    inverter_host: Optional[str]
    inverter_port: int
    inverter_slave_id: int
    fusion_username: Optional[str]
    fusion_password: Optional[str]
    fusion_subdomain: str
    fusion_plant_id: Optional[str]
    ntfy_url: str
    ntfy_topic: str
    poll_interval_s: int
    increase_threshold_w: float
    decrease_threshold_w: float
    hysteresis_w: float
    battery_low_soc_pct: float
    battery_low_hysteresis_pct: float
    grid_import_alert_w: float
    grid_import_alert_min_pv_w: float
    cooldown_minutes: int
    renotify_minutes: int
    grid_export_positive: bool
    battery_charge_positive: bool
    daily_summary_enabled: bool
    daily_summary_hour: int


def load_config() -> Config:
    data_source = os.getenv("DATA_SOURCE", "modbus").strip().lower()
    if data_source not in ("modbus", "cloud"):
        raise ValueError(f"DATA_SOURCE must be 'modbus' or 'cloud', got {data_source!r}")

    inverter_host = os.getenv("INVERTER_HOST")
    fusion_username = os.getenv("FUSIONSOLAR_USERNAME")
    fusion_password = os.getenv("FUSIONSOLAR_PASSWORD")

    if data_source == "modbus" and not inverter_host:
        raise ValueError("INVERTER_HOST is required when DATA_SOURCE=modbus")
    if data_source == "cloud" and not (fusion_username and fusion_password):
        raise ValueError(
            "FUSIONSOLAR_USERNAME and FUSIONSOLAR_PASSWORD are required when DATA_SOURCE=cloud"
        )

    return Config(
        data_source=data_source,
        inverter_host=inverter_host,
        inverter_port=_get_int("INVERTER_PORT", 502),
        inverter_slave_id=_get_int("INVERTER_SLAVE_ID", 0),
        fusion_username=fusion_username,
        fusion_password=fusion_password,
        fusion_subdomain=os.getenv("FUSIONSOLAR_SUBDOMAIN", "region01eu5"),
        fusion_plant_id=os.getenv("FUSIONSOLAR_PLANT_ID"),
        ntfy_url=os.getenv("NTFY_URL", "https://ntfy.sh"),
        ntfy_topic=os.environ["NTFY_TOPIC"],
        poll_interval_s=_get_int("POLL_INTERVAL_SECONDS", 60),
        increase_threshold_w=_get_float("INCREASE_THRESHOLD_W", 1000),
        decrease_threshold_w=_get_float("DECREASE_THRESHOLD_W", 1000),
        hysteresis_w=_get_float("HYSTERESIS_W", 200),
        battery_low_soc_pct=_get_float("BATTERY_LOW_SOC_PCT", 95),
        battery_low_hysteresis_pct=_get_float("BATTERY_LOW_HYSTERESIS_PCT", 2),
        grid_import_alert_w=_get_float("GRID_IMPORT_ALERT_W", 200),
        grid_import_alert_min_pv_w=_get_float("GRID_IMPORT_ALERT_MIN_PV_W", 500),
        cooldown_minutes=_get_int("COOLDOWN_MINUTES", 15),
        renotify_minutes=_get_int("RENOTIFY_MINUTES", 45),
        grid_export_positive=_get_bool("GRID_EXPORT_POSITIVE", True),
        battery_charge_positive=_get_bool("BATTERY_CHARGE_POSITIVE", True),
        daily_summary_enabled=_get_bool("DAILY_SUMMARY_ENABLED", True),
        daily_summary_hour=_get_int("DAILY_SUMMARY_HOUR", 21),
    )
