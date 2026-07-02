import asyncio
import logging
from typing import Any, Optional

from fusion_solar_py.client import FusionSolarClient

from solar_push.inverter import InverterReading

log = logging.getLogger(__name__)


def _extract_grid_power_w(flow: dict) -> Optional[float]:
    """Best-effort search for the grid power node in a FusionSolar energy-flow response.

    fusion-solar-py returns get_plant_flow() as a raw, undocumented dict (the
    structure behind the FusionSolar UI's flow diagram). There's no verified
    schema for it, so this walks the structure looking for a node whose label
    mentions "grid"/"netz" with a numeric value, instead of indexing fixed
    keys that might not match your account's response shape.

    Whatever this returns should be checked with scripts/dump_fusion_solar_flow.py
    against a real account before being trusted for automated decisions - both
    the extraction and the sign (import vs. export) are unverified.
    """

    def walk(node: Any) -> Optional[float]:
        if isinstance(node, dict):
            label = str(node.get("name") or node.get("label") or node.get("description") or "").lower()
            if "grid" in label or "netz" in label:
                raw_value = node.get("value") or node.get("realValue")
                if raw_value is not None:
                    try:
                        numeric = float(str(raw_value).lower().replace("kw", "").replace("w", "").strip())
                    except ValueError:
                        pass
                    else:
                        # values containing "kw" were in kW, everything else assumed W
                        is_kw = "kw" in str(raw_value).lower()
                        return numeric * 1000 if is_kw else numeric
            for value in node.values():
                result = walk(value)
                if result is not None:
                    return result
        elif isinstance(node, list):
            for item in node:
                result = walk(item)
                if result is not None:
                    return result
        return None

    return walk(flow)


class CloudInverter:
    """Reads live power values via the Huawei FusionSolar cloud portal instead of local Modbus.

    Uses the unofficial, reverse-engineered fusion-solar-py client - no LAN
    access to the inverter needed, at the cost of an unofficial API that
    Huawei could change or block at any time, several minutes of data lag
    compared to local Modbus, and your FusionSolar account password living
    in the environment. Grid power extraction is best-effort (see
    _extract_grid_power_w); PV power and battery SOC use documented,
    stable client methods.
    """

    def __init__(
        self,
        username: str,
        password: str,
        subdomain: str,
        plant_id: Optional[str],
        grid_export_positive: bool,
    ):
        self._username = username
        self._password = password
        self._subdomain = subdomain
        self._plant_id = plant_id
        self._grid_sign = 1 if grid_export_positive else -1
        self._client: Optional[FusionSolarClient] = None
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

        try:
            battery_ids = await asyncio.to_thread(self._client.get_battery_ids, self._plant_id)
            self._battery_id = battery_ids[0] if battery_ids else None
        except Exception:
            self._battery_id = None  # no battery installed / not readable

    async def close(self) -> None:
        if self._client is not None:
            await asyncio.to_thread(self._client.log_out)

    async def read(self) -> InverterReading:
        assert self._client is not None, "call connect() first"

        power_status = await asyncio.to_thread(self._client.get_power_status)
        pv_power_w = power_status.current_power_kw * 1000

        grid_power_w = None
        try:
            flow = await asyncio.to_thread(self._client.get_plant_flow, self._plant_id)
            grid_power_w = _extract_grid_power_w(flow)
            if grid_power_w is not None:
                grid_power_w *= self._grid_sign
        except Exception:
            log.debug("Failed to read grid power from FusionSolar plant flow", exc_info=True)

        battery_soc_pct = None
        if self._battery_id is not None:
            try:
                battery_status = await asyncio.to_thread(
                    self._client.get_battery_basic_stats, self._battery_id
                )
                battery_soc_pct = battery_status.state_of_charge
            except Exception:
                log.debug("Failed to read battery status from FusionSolar", exc_info=True)

        return InverterReading(
            pv_power_w=pv_power_w,
            grid_power_w=grid_power_w,
            battery_soc_pct=battery_soc_pct,
        )
