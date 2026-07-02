from datetime import datetime, timedelta

from solar_push.logic import Evaluator, ThresholdWatcher


def make_evaluator(**overrides):
    defaults = dict(
        increase_threshold_w=1000,
        decrease_threshold_w=1000,
        hysteresis_w=200,
        battery_low_soc_pct=95,
        battery_low_hysteresis_pct=2,
        cooldown_minutes=15,
        renotify_minutes=45,
    )
    defaults.update(overrides)
    return Evaluator(**defaults)


def titles(decisions):
    return [d.title for d in decisions]


def test_normal_values_do_not_notify():
    ev = make_evaluator()
    decisions = ev.evaluate(
        grid_power_w=500, battery_discharge_w=200, battery_soc_pct=98, now=datetime(2024, 1, 1, 12, 0)
    )
    assert decisions == []


def test_surplus_crossing_threshold_notifies_once():
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 12, 0)
    d1 = ev.evaluate(grid_power_w=1500, now=t0)
    assert "☀️ Stromüberschuss" in titles(d1)

    d2 = ev.evaluate(grid_power_w=1600, now=t0 + timedelta(minutes=1))
    assert d2 == []  # still in cooldown / not due for renotify


def test_battery_drain_crossing_threshold_notifies():
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 18, 0)
    d1 = ev.evaluate(battery_discharge_w=1500, now=t0)
    assert "⚠️ Speicher wird stark entladen" in titles(d1)


def test_battery_low_soc_notifies():
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 20, 0)
    d1 = ev.evaluate(battery_soc_pct=90, now=t0)
    assert "🔋 Speicher niedrig" in titles(d1)


def test_grid_and_battery_signals_are_independent():
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 12, 0)
    decisions = ev.evaluate(grid_power_w=1500, battery_discharge_w=1500, battery_soc_pct=90, now=t0)
    assert set(titles(decisions)) == {
        "☀️ Stromüberschuss",
        "⚠️ Speicher wird stark entladen",
        "🔋 Speicher niedrig",
    }


def test_hysteresis_prevents_flapping_near_threshold():
    watcher = ThresholdWatcher(
        threshold=1000, hysteresis=200, cooldown_minutes=15, renotify_minutes=45, direction="above"
    )
    t0 = datetime(2024, 1, 1, 12, 0)
    assert watcher.evaluate(1500, now=t0) is True  # enters active state, notifies

    # Dips just below the raw threshold but still within the hysteresis band.
    assert watcher.evaluate(900, now=t0 + timedelta(minutes=1)) is False

    # Drops below threshold - hysteresis -> back to inactive, no notification.
    assert watcher.evaluate(700, now=t0 + timedelta(minutes=2)) is False


def test_renotify_after_interval_while_condition_persists():
    watcher = ThresholdWatcher(
        threshold=1000, hysteresis=200, cooldown_minutes=15, renotify_minutes=45, direction="above"
    )
    t0 = datetime(2024, 1, 1, 12, 0)
    assert watcher.evaluate(1500, now=t0) is True

    too_soon = watcher.evaluate(1500, now=t0 + timedelta(minutes=20))
    assert too_soon is False

    due = watcher.evaluate(1500, now=t0 + timedelta(minutes=46))
    assert due is True


def test_cooldown_blocks_immediate_flap_renotify():
    watcher = ThresholdWatcher(
        threshold=1000, hysteresis=200, cooldown_minutes=15, renotify_minutes=1, direction="above"
    )
    t0 = datetime(2024, 1, 1, 12, 0)
    assert watcher.evaluate(1500, now=t0) is True  # notifies

    # Flap below and back above within the cooldown window - should not spam.
    watcher.evaluate(700, now=t0 + timedelta(minutes=1))
    assert watcher.evaluate(1500, now=t0 + timedelta(minutes=2)) is False


def test_below_direction_for_low_battery_soc():
    watcher = ThresholdWatcher(
        threshold=95, hysteresis=2, cooldown_minutes=15, renotify_minutes=45, direction="below"
    )
    t0 = datetime(2024, 1, 1, 12, 0)
    assert watcher.evaluate(98, now=t0) is False  # above threshold, not low
    assert watcher.evaluate(90, now=t0 + timedelta(minutes=1)) is True  # crosses below, notifies

    # Recovers just above threshold but within hysteresis band -> stays "low".
    assert watcher.evaluate(96, now=t0 + timedelta(minutes=2)) is False

    # Recovers past the hysteresis band -> no longer low.
    assert watcher.evaluate(98, now=t0 + timedelta(minutes=3)) is False
