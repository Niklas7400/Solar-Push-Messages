from dataclasses import dataclass
from typing import Optional

from huawei_solar import HuaweiSolarBridge
from huawei_solar import register_names as rn


@dataclass
class InverterReading:
    pv_power_w: float
    grid_power_w: Optional[float]
    battery_soc_pct: Optional[float]


class Inverter:
    """Reads live power values from a Huawei SUN2000 inverter over local Modbus TCP.

    grid_power_w follows the "surplus is positive" convention: positive means
    power is flowing out to the grid, negative means power is being drawn
    from the grid. Raw meter polarity varies by installation, so the sign is
    normalized here based on Config.grid_export_positive.
    """

    def __init__(self, host: str, port: int, slave_id: int, grid_export_positive: bool):
        self._host = host
        self._port = port
        self._slave_id = slave_id
        self._grid_sign = 1 if grid_export_positive else -1
        self._bridge: Optional[HuaweiSolarBridge] = None

    async def connect(self) -> None:
        self._bridge = await HuaweiSolarBridge.create(
            host=self._host, port=self._port, slave_id=self._slave_id
        )

    async def close(self) -> None:
        if self._bridge is not None:
            await self._bridge.stop()

    async def read(self) -> InverterReading:
        assert self._bridge is not None, "call connect() first"

        pv_power_w = (await self._bridge.batch_update([rn.INPUT_POWER]))[
            rn.INPUT_POWER
        ].value

        grid_power_w = None
        try:
            raw_grid = (
                await self._bridge.batch_update([rn.POWER_METER_ACTIVE_POWER])
            )[rn.POWER_METER_ACTIVE_POWER].value
            grid_power_w = raw_grid * self._grid_sign
        except Exception:
            pass  # no power meter installed / not readable

        battery_soc_pct = None
        try:
            battery_soc_pct = (
                await self._bridge.batch_update([rn.STORAGE_STATE_OF_CAPACITY])
            )[rn.STORAGE_STATE_OF_CAPACITY].value
        except Exception:
            pass  # no battery installed / not readable

        return InverterReading(
            pv_power_w=pv_power_w,
            grid_power_w=grid_power_w,
            battery_soc_pct=battery_soc_pct,
        )
