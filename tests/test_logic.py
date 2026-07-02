from datetime import datetime, timedelta

from solar_push.daily_summary import DailyEnergyTracker
from solar_push.logic import Evaluator, ThresholdWatcher


def make_evaluator(**overrides):
    defaults = dict(
        increase_threshold_w=1000,
        decrease_threshold_w=1000,
        hysteresis_w=200,
        battery_low_soc_pct=95,
        battery_low_hysteresis_pct=2,
        grid_import_alert_w=200,
        grid_import_alert_min_pv_w=500,
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


def test_grid_import_above_alert_notifies_with_enough_pv():
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 13, 0)
    d1 = ev.evaluate(grid_power_w=-300, pv_power_w=800, now=t0)
    assert "⚡ Netzbezug erkannt" in titles(d1)
    assert d1[0].priority == "urgent"


def test_small_grid_import_does_not_notify():
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 13, 0)
    d1 = ev.evaluate(grid_power_w=-50, pv_power_w=800, now=t0)
    assert d1 == []


def test_grid_import_at_night_does_not_notify():
    # Same import as the "notifies" case above, but without enough PV -
    # this is the normal nightly situation and shouldn't alert.
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 22, 0)
    d1 = ev.evaluate(grid_power_w=-300, pv_power_w=0, now=t0)
    assert d1 == []

    d2 = ev.evaluate(grid_power_w=-300, pv_power_w=None, now=t0 + timedelta(minutes=1))
    assert d2 == []


def test_grid_and_battery_signals_are_independent():
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 12, 0)
    decisions = ev.evaluate(grid_power_w=1500, battery_discharge_w=1500, battery_soc_pct=90, now=t0)
    assert set(titles(decisions)) == {
        "☀️ Stromüberschuss",
        "⚠️ Speicher wird stark entladen",
        "🔋 Speicher niedrig",
    }


def test_message_includes_pv_and_battery_context():
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 12, 0)
    decisions = ev.evaluate(grid_power_w=1500, pv_power_w=2200, battery_soc_pct=80, now=t0)
    assert "PV: 2200 W" in decisions[0].message
    assert "Speicher: 80 %" in decisions[0].message


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


def test_daily_summary_accumulates_and_fires_once_after_hour():
    tracker = DailyEnergyTracker(summary_hour=21)
    day = datetime(2024, 6, 1, 10, 0)

    # Two hours of 2000W PV, 500W export, no import.
    tracker.add(pv_power_w=2000, grid_power_w=500, poll_interval_s=3600, now=day)
    tracker.add(pv_power_w=2000, grid_power_w=500, poll_interval_s=3600, now=day + timedelta(hours=1))

    assert tracker.maybe_build_summary(day + timedelta(hours=2)) is None  # before summary_hour

    summary = tracker.maybe_build_summary(day.replace(hour=21))
    assert summary is not None
    assert "4.0 kWh" in summary.message  # PV
    assert "1.0 kWh" in summary.message  # export
    assert summary.priority == "low"

    # Only fires once per day.
    assert tracker.maybe_build_summary(day.replace(hour=22)) is None


def test_daily_summary_resets_on_new_day():
    tracker = DailyEnergyTracker(summary_hour=21)
    day1 = datetime(2024, 6, 1, 21, 0)
    tracker.add(pv_power_w=1000, grid_power_w=-200, poll_interval_s=3600, now=day1)
    assert tracker.maybe_build_summary(day1) is not None

    day2 = datetime(2024, 6, 2, 21, 0)
    tracker.add(pv_power_w=500, grid_power_w=0, poll_interval_s=3600, now=day2)
    summary = tracker.maybe_build_summary(day2)
    assert summary is not None
    assert "0.5 kWh" in summary.message  # only day2's contribution, not carried over
