from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional


@dataclass
class Decision:
    title: str
    message: str
    priority: str = "default"  # ntfy priority: min|low|default|high|urgent


class ThresholdWatcher:
    """Tracks whether a value has crossed a threshold and decides when to notify.

    Uses hysteresis around the threshold (to avoid flapping when the value
    hovers right at the limit) plus a cooldown and a re-notify interval (so
    a sustained condition reminds the user again after a while instead of
    firing once and going silent).

    direction="above": active while value >= threshold (e.g. surplus power).
    direction="below": active while value <= threshold (e.g. low battery SOC).
    """

    def __init__(
        self,
        threshold: float,
        hysteresis: float,
        cooldown_minutes: int,
        renotify_minutes: int,
        direction: str = "above",
    ):
        if direction not in ("above", "below"):
            raise ValueError("direction must be 'above' or 'below'")
        self._threshold = threshold
        self._hysteresis = hysteresis
        self._cooldown = timedelta(minutes=cooldown_minutes)
        self._renotify = timedelta(minutes=renotify_minutes)
        self._direction = direction
        self._active = False
        self._last_notified_at: Optional[datetime] = None

    def _crosses(self, value: float) -> bool:
        if self._direction == "above":
            return value >= self._threshold
        return value <= self._threshold

    def _stays_active(self, value: float) -> bool:
        if self._direction == "above":
            return value >= self._threshold - self._hysteresis
        return value <= self._threshold + self._hysteresis

    def evaluate(self, value: float, now: Optional[datetime] = None) -> bool:
        """Update state for the latest value and return whether to notify now."""
        now = now or datetime.now()
        new_active = self._stays_active(value) if self._active else self._crosses(value)
        became_active = new_active and not self._active

        cooldown_over = (
            self._last_notified_at is None or now - self._last_notified_at >= self._cooldown
        )
        due_for_renotify = (
            self._last_notified_at is not None and now - self._last_notified_at >= self._renotify
        )

        should_notify = new_active and cooldown_over and (became_active or due_for_renotify)

        self._active = new_active
        if should_notify:
            self._last_notified_at = now

        return should_notify


def _context_suffix(pv_power_w: Optional[float], battery_soc_pct: Optional[float] = None) -> str:
    bits = []
    if pv_power_w is not None:
        bits.append(f"PV: {pv_power_w:.0f} W")
    if battery_soc_pct is not None:
        bits.append(f"Speicher: {battery_soc_pct:.0f} %")
    return f"\n\n{' | '.join(bits)}" if bits else ""


class Evaluator:
    """Turns live inverter readings into a list of notifications to send.

    Four independent conditions, each with its own hysteresis/cooldown/renotify:
    - grid surplus (grid_power_w >= increase_threshold_w): good time to use power.
    - battery draining fast (battery_discharge_w >= decrease_threshold_w): reduce
      consumption before the battery runs low and the grid has to pick up the load.
    - battery low (battery_soc_pct <= battery_low_soc_pct): plan around it.
    - unexpected grid import (grid_power_w <= -grid_import_alert_w), only while
      pv_power_w >= grid_import_alert_min_pv_w: flags a notable draw from the
      grid despite the sun being up, when PV (+ battery) should normally cover
      it. Not gated on daylight, this would fire every night as PV drops to 0.
    """

    def __init__(
        self,
        increase_threshold_w: float,
        decrease_threshold_w: float,
        hysteresis_w: float,
        battery_low_soc_pct: float,
        battery_low_hysteresis_pct: float,
        grid_import_alert_w: float,
        grid_import_alert_min_pv_w: float,
        cooldown_minutes: int,
        renotify_minutes: int,
    ):
        self._grid_import_alert_min_pv_w = grid_import_alert_min_pv_w
        self._surplus = ThresholdWatcher(
            increase_threshold_w, hysteresis_w, cooldown_minutes, renotify_minutes, "above"
        )
        self._battery_drain = ThresholdWatcher(
            decrease_threshold_w, hysteresis_w, cooldown_minutes, renotify_minutes, "above"
        )
        self._battery_low = ThresholdWatcher(
            battery_low_soc_pct,
            battery_low_hysteresis_pct,
            cooldown_minutes,
            renotify_minutes,
            "below",
        )
        self._grid_import = ThresholdWatcher(
            -grid_import_alert_w, hysteresis_w, cooldown_minutes, renotify_minutes, "below"
        )

    def evaluate(
        self,
        grid_power_w: Optional[float] = None,
        battery_discharge_w: Optional[float] = None,
        battery_soc_pct: Optional[float] = None,
        pv_power_w: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> List[Decision]:
        decisions: List[Decision] = []

        if grid_power_w is not None and self._surplus.evaluate(grid_power_w, now):
            decisions.append(
                Decision(
                    title="☀️ Stromüberschuss",
                    message=(
                        f"Aktuell {grid_power_w:.0f} W Überschuss – jetzt Verbraucher "
                        "einschalten (Waschmaschine, Trockner, Wärmepumpe, Laden...)."
                        + _context_suffix(pv_power_w, battery_soc_pct)
                    ),
                )
            )

        if battery_discharge_w is not None and self._battery_drain.evaluate(
            battery_discharge_w, now
        ):
            decisions.append(
                Decision(
                    title="⚠️ Speicher wird stark entladen",
                    message=(
                        f"Aktuell {battery_discharge_w:.0f} W Entladeleistung aus dem "
                        "Speicher – Verbrauch reduzieren empfohlen."
                        + _context_suffix(pv_power_w, battery_soc_pct)
                    ),
                )
            )

        if battery_soc_pct is not None and self._battery_low.evaluate(battery_soc_pct, now):
            decisions.append(
                Decision(
                    title="🔋 Speicher niedrig",
                    message=f"Ladestand aktuell {battery_soc_pct:.0f} %." + _context_suffix(pv_power_w),
                )
            )

        # Only counts as an anomaly while there's enough PV to expect it to
        # cover consumption - otherwise this fires every single night.
        has_enough_pv = pv_power_w is not None and pv_power_w >= self._grid_import_alert_min_pv_w
        if grid_power_w is not None:
            notify = (
                self._grid_import.evaluate(grid_power_w, now)
                if has_enough_pv
                else self._grid_import.evaluate(0, now)
            )
            if notify:
                decisions.append(
                    Decision(
                        title="⚡ Netzbezug erkannt",
                        message=(
                            f"Aktuell {abs(grid_power_w):.0f} W Bezug vom Netz trotz "
                            f"{pv_power_w:.0f} W PV-Leistung – ungewöhnlich, ggf. "
                            "Ursache prüfen." + _context_suffix(None, battery_soc_pct)
                        ),
                        priority="urgent",
                    )
                )

        return decisions
