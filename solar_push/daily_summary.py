from datetime import date, datetime
from typing import Optional

from solar_push.logic import Decision


class DailyEnergyTracker:
    """Integrates power readings into daily energy totals and builds an evening summary.

    Totals are computed by the running process itself (power * time, summed
    per poll) rather than read from vendor daily-energy registers/signals -
    this works identically for both the local Modbus and cloud backends, at
    the cost of only covering time the service was actually running (no
    backfill across restarts, and accuracy is bounded by poll_interval_s).
    """

    def __init__(self, summary_hour: int):
        self._summary_hour = summary_hour
        self._pv_kwh = 0.0
        self._export_kwh = 0.0
        self._import_kwh = 0.0
        self._tracking_date: Optional[date] = None
        self._last_summary_date: Optional[date] = None

    def add(
        self,
        pv_power_w: float,
        grid_power_w: Optional[float],
        poll_interval_s: int,
        now: Optional[datetime] = None,
    ) -> None:
        now = now or datetime.now()
        if self._tracking_date is not None and now.date() != self._tracking_date:
            self._pv_kwh = self._export_kwh = self._import_kwh = 0.0
        self._tracking_date = now.date()

        hours = poll_interval_s / 3600
        self._pv_kwh += pv_power_w * hours / 1000
        if grid_power_w is not None:
            if grid_power_w > 0:
                self._export_kwh += grid_power_w * hours / 1000
            else:
                self._import_kwh += -grid_power_w * hours / 1000

    def maybe_build_summary(self, now: Optional[datetime] = None) -> Optional[Decision]:
        now = now or datetime.now()
        if now.hour < self._summary_hour or self._last_summary_date == now.date():
            return None
        self._last_summary_date = now.date()

        return Decision(
            title="📊 Tagesbericht",
            message=(
                f"PV-Ertrag: {self._pv_kwh:.1f} kWh | "
                f"Eingespeist: {self._export_kwh:.1f} kWh | "
                f"Netzbezug: {self._import_kwh:.1f} kWh"
            ),
            priority="low",
        )
