import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from nissan_leaf.kamereon.kamereon import NCISession
from nissan_leaf.kamereon.kamereon_const import ChargingStatus, PluggedStatus

log = logging.getLogger(__name__)


@dataclass
class LeafReading:
    battery_level_pct: Optional[float]
    charging: Optional[bool]
    plugged_in: Optional[bool]


class NissanLeaf:
    """Reads battery/charge status via the NissanConnect Services cloud API (EU only).

    Uses a vendored copy of the unofficial kamereon client from
    dan-r/HomeAssistant-NissanConnect (see nissan_leaf/kamereon/NOTICE.md) -
    an unofficial, reverse-engineered API that Nissan could change or block
    at any time.

    Each read() actively wakes the car (refresh_battery_status) before
    reading, rather than relying on whatever it last reported on its own -
    the cloud cache can otherwise sit hours stale. At a 10-minute poll
    interval this is a fairly light touch, but it does mean the car's
    telematics unit gets woken up every poll, which EV owner communities
    associate with extra 12V battery drain over time - worth keeping an eye
    on if the poll interval is lowered.
    """

    def __init__(
        self,
        username: str,
        password: str,
        vin: Optional[str] = None,
        refresh_wait_s: float = 25,
    ):
        self._username = username
        self._password = password
        self._vin = vin.upper() if vin else None
        self._refresh_wait_s = refresh_wait_s
        self._session: Optional[NCISession] = None
        self._vehicle = None

    async def connect(self) -> None:
        self._session = NCISession(region="EU")
        await asyncio.to_thread(self._session.login, self._username, self._password)

        vehicles = await asyncio.to_thread(self._session.fetch_vehicles)
        if not vehicles:
            raise RuntimeError("No vehicles found on this NissanConnect account")

        if self._vin is not None:
            self._vehicle = next((v for v in vehicles if v.vin == self._vin), None)
            if self._vehicle is None:
                found = ", ".join(v.vin for v in vehicles)
                raise RuntimeError(f"VIN {self._vin} not found among account vehicles: {found}")
        else:
            self._vehicle = vehicles[0]

    async def close(self) -> None:
        pass  # kamereon client has no explicit logout/session teardown

    async def read(self) -> LeafReading:
        assert self._vehicle is not None, "call connect() first"

        try:
            await asyncio.to_thread(self._vehicle.refresh_battery_status)
            await asyncio.sleep(self._refresh_wait_s)
        except Exception:
            log.warning(
                "Failed to trigger active battery status refresh, falling back to cached data",
                exc_info=True,
            )

        await asyncio.to_thread(self._vehicle.fetch_battery_status)

        charging = None
        if self._vehicle.charging is not None:
            charging = self._vehicle.charging == ChargingStatus.CHARGING

        plugged_in = None
        if self._vehicle.plugged_in is not None:
            plugged_in = self._vehicle.plugged_in == PluggedStatus.PLUGGED

        return LeafReading(
            battery_level_pct=self._vehicle.battery_level,
            charging=charging,
            plugged_in=plugged_in,
        )
