from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional


class GridState(Enum):
    NORMAL = auto()
    SURPLUS = auto()  # exporting power -> good time to increase consumption
    DEFICIT = auto()  # importing power -> should reduce consumption


@dataclass
class Decision:
    state: GridState
    should_notify: bool
    title: Optional[str] = None
    message: Optional[str] = None


class Evaluator:
    """Turns a grid power reading into a notify/don't-notify decision.

    Uses hysteresis around the thresholds (to avoid flapping when the power
    value hovers right at the limit) plus a cooldown and a re-notify
    interval (so a sustained surplus/deficit reminds the user again after a
    while instead of firing once and going silent).
    """

    def __init__(
        self,
        increase_threshold_w: float,
        decrease_threshold_w: float,
        hysteresis_w: float,
        cooldown_minutes: int,
        renotify_minutes: int,
    ):
        self._increase_threshold = increase_threshold_w
        self._decrease_threshold = decrease_threshold_w
        self._hysteresis = hysteresis_w
        self._cooldown = timedelta(minutes=cooldown_minutes)
        self._renotify = timedelta(minutes=renotify_minutes)
        self._state = GridState.NORMAL
        self._last_notified_at: Optional[datetime] = None

    def _classify_from_normal(self, grid_power_w: float) -> GridState:
        if grid_power_w >= self._increase_threshold:
            return GridState.SURPLUS
        if grid_power_w <= -self._decrease_threshold:
            return GridState.DEFICIT
        return GridState.NORMAL

    def _next_state(self, grid_power_w: float) -> GridState:
        if self._state == GridState.SURPLUS:
            if grid_power_w >= self._increase_threshold - self._hysteresis:
                return GridState.SURPLUS
            return self._classify_from_normal(grid_power_w)
        if self._state == GridState.DEFICIT:
            if grid_power_w <= -self._decrease_threshold + self._hysteresis:
                return GridState.DEFICIT
            return self._classify_from_normal(grid_power_w)
        return self._classify_from_normal(grid_power_w)

    def evaluate(self, grid_power_w: float, now: Optional[datetime] = None) -> Decision:
        now = now or datetime.now()
        new_state = self._next_state(grid_power_w)
        state_changed = new_state != self._state

        cooldown_over = (
            self._last_notified_at is None or now - self._last_notified_at >= self._cooldown
        )
        due_for_renotify = (
            self._last_notified_at is not None and now - self._last_notified_at >= self._renotify
        )

        should_notify = False
        title = None
        message = None

        if new_state != GridState.NORMAL and cooldown_over and (state_changed or due_for_renotify):
            should_notify = True
            if new_state == GridState.SURPLUS:
                title = "☀️ Stromüberschuss"
                message = (
                    f"Aktuell {grid_power_w:.0f} W Überschuss – jetzt Verbraucher "
                    "einschalten (Waschmaschine, Trockner, Wärmepumpe, Laden...)."
                )
            else:
                title = "⚠️ Netzbezug hoch"
                message = (
                    f"Aktuell {abs(grid_power_w):.0f} W Bezug vom Netz – "
                    "Verbrauch reduzieren empfohlen."
                )

        self._state = new_state
        if should_notify:
            self._last_notified_at = now

        return Decision(state=new_state, should_notify=should_notify, title=title, message=message)
