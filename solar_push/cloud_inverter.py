import asyncio
import logging
from typing import Optional

from fusion_solar_py.client import FusionSolarClient

from solar_push.inverter import InverterReading

log = logging.getLogger(__name__)


def _get_signal(real_time_data: dict, signal_name: str) -> Optional[float]:
    """Look up a named signal (e.g. "Active power") in a get_real_time_data() response."""
    for group in real_time_data.get("data", []):
        for signal in group.get("signals", []):
            if signal.get("name") == signal_name:
                try:
                    return float(signal["realValue"])
                except (KeyError, TypeError, ValueError):
                    return None
    return None


class CloudInverter:
    """Reads live power values via the Huawei FusionSolar cloud portal instead of local Modbus.

    Uses the unofficial, reverse-engineered fusion-solar-py client - no LAN
    access to the inverter needed, at the cost of an unofficial API that
    Huawei could change or block at any time, several minutes of data lag
    compared to local Modbus, and your FusionSolar account password living
    in the environment.

    Grid power is read as the "Active power" signal directly off the meter
    device ("Power Sensor" in get_device_ids()) via get_real_time_data() -
    verified against a real account to carry the same sign convention as the
    local Modbus power_meter_active_power register (positive = exporting to
    the grid), since it's the same physical Smart Power Sensor either way.

    battery_discharge_w follows the "discharging is positive" convention.
    get_battery_basic_stats().current_charge_discharge_kw is commonly
    documented as positive-while-charging for Huawei systems, so the sign
    is normalized here based on battery_charge_positive - not yet verified
    against a real charge/discharge event (the test account's battery was
    idle), flip it if it comes out backwards in practice.
    """

    def __init__(
        self,
        username: str,
        password: str,
        subdomain: str,
        plant_id: Optional[str],
        grid_export_positive: bool,
        battery_charge_positive: bool = True,
    ):
        self._username = username
        self._password = password
        self._subdomain = subdomain
        self._plant_id = plant_id
        self._grid_sign = 1 if grid_export_positive else -1
        self._battery_discharge_sign = -1 if battery_charge_positive else 1
        self._client: Optional[FusionSolarClient] = None
        self._meter_dn: Optional[str] = None
        self._battery_id: Optional[str] = None

    async def connect(self) -> None:
        self._client = await asyncio.to_thread(
            FusionSolarClient, self._username, self._password, huawei_subdomain=self._subdomain
        )

        if self._plant_id is None:
            plant_ids = await asyncio.to_thread(self._client.get_plant_ids)
            if not plant_ids:
                raise RuntimeError("No FusionSolar plants found for this account")
            self._plant_id = plant_ids[0]

        devices = await asyncio.to_thread(self._client.get_device_ids)
        meter = next((d for d in devices if d["type"] == "Power Sensor"), None)
        self._meter_dn = meter["deviceDn"] if meter else None
        if self._meter_dn is None:
            log.warning(
                "No 'Power Sensor' (Smart Power Sensor) device found on this FusionSolar "
                "account. Without it, grid power can't be read and notifications won't fire."
            )

        try:
            battery_ids = await asyncio.to_thread(self._client.get_battery_ids, self._plant_id)
            self._battery_id = battery_ids[0] if battery_ids else None
        except Exception:
            self._battery_id = None  # no battery installed / not readable
            log.warning("Failed to discover battery for FusionSolar plant", exc_info=True)

    async def close(self) -> None:
        if self._client is not None:
            await asyncio.to_thread(self._client.log_out)

    async def read(self) -> InverterReading:
        assert self._client is not None, "call connect() first"

        power_status = await asyncio.to_thread(self._client.get_power_status)
        pv_power_w = power_status.current_power_kw * 1000

        grid_power_w = None
        if self._meter_dn is not None:
            try:
                meter_data = await asyncio.to_thread(self._client.get_real_time_data, self._meter_dn)
                grid_power_w = _get_signal(meter_data, "Active power")
                if grid_power_w is not None:
                    grid_power_w *= self._grid_sign
            except Exception:
                log.warning("Failed to read grid power from FusionSolar meter", exc_info=True)

        battery_soc_pct = None
        battery_discharge_w = None
        if self._battery_id is not None:
            try:
                battery_status = await asyncio.to_thread(
                    self._client.get_battery_basic_stats, self._battery_id
                )
                battery_soc_pct = battery_status.state_of_charge
                battery_discharge_w = (
                    battery_status.current_charge_discharge_kw * 1000 * self._battery_discharge_sign
                )
            except Exception:
                log.warning("Failed to read battery status from FusionSolar", exc_info=True)

        return InverterReading(
            pv_power_w=pv_power_w,
            grid_power_w=grid_power_w,
            battery_soc_pct=battery_soc_pct,
            battery_discharge_w=battery_discharge_w,
        )
