from datetime import datetime, timedelta

from solar_push.logic import Evaluator, GridState


def make_evaluator(**overrides):
    defaults = dict(
        increase_threshold_w=1000,
        decrease_threshold_w=1000,
        hysteresis_w=200,
        cooldown_minutes=15,
        renotify_minutes=45,
    )
    defaults.update(overrides)
    return Evaluator(**defaults)


def test_normal_power_does_not_notify():
    ev = make_evaluator()
    decision = ev.evaluate(500, now=datetime(2024, 1, 1, 12, 0))
    assert decision.state == GridState.NORMAL
    assert decision.should_notify is False


def test_surplus_crossing_threshold_notifies_once():
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 12, 0)
    d1 = ev.evaluate(1500, now=t0)
    assert d1.state == GridState.SURPLUS
    assert d1.should_notify is True
    assert "Strom" in d1.title

    d2 = ev.evaluate(1600, now=t0 + timedelta(minutes=1))
    assert d2.state == GridState.SURPLUS
    assert d2.should_notify is False  # still in cooldown / not due for renotify


def test_deficit_crossing_threshold_notifies():
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 18, 0)
    d1 = ev.evaluate(-1500, now=t0)
    assert d1.state == GridState.DEFICIT
    assert d1.should_notify is True
    assert "Netzbezug" in d1.title


def test_hysteresis_prevents_flapping_near_threshold():
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 12, 0)
    ev.evaluate(1500, now=t0)  # enters SURPLUS

    # Dips just below the raw threshold but still within the hysteresis band.
    d2 = ev.evaluate(900, now=t0 + timedelta(minutes=1))
    assert d2.state == GridState.SURPLUS
    assert d2.should_notify is False

    # Drops below threshold - hysteresis -> back to NORMAL, no notification.
    d3 = ev.evaluate(700, now=t0 + timedelta(minutes=2))
    assert d3.state == GridState.NORMAL
    assert d3.should_notify is False


def test_renotify_after_interval_while_still_in_surplus():
    ev = make_evaluator()
    t0 = datetime(2024, 1, 1, 12, 0)
    ev.evaluate(1500, now=t0)

    too_soon = ev.evaluate(1500, now=t0 + timedelta(minutes=20))
    assert too_soon.should_notify is False

    due = ev.evaluate(1500, now=t0 + timedelta(minutes=46))
    assert due.should_notify is True


def test_cooldown_blocks_immediate_flap_renotify():
    ev = make_evaluator(cooldown_minutes=15, renotify_minutes=1)
    t0 = datetime(2024, 1, 1, 12, 0)
    ev.evaluate(1500, now=t0)  # SURPLUS, notifies

    # Flap to DEFICIT and back within the cooldown window - should not spam.
    ev.evaluate(-1500, now=t0 + timedelta(minutes=1))
    d = ev.evaluate(1500, now=t0 + timedelta(minutes=2))
    assert d.should_notify is False
