import asyncio
import logging

from solar_push.logic import ThresholdWatcher
from solar_push.notifier import Notifier

from nissan_leaf.config import load_nissan_config
from nissan_leaf.vehicle import NissanLeaf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nissan_leaf")


async def run(debug: bool) -> None:
    config = load_nissan_config()
    leaf = NissanLeaf(
        username=config.username,
        password=config.password,
        vin=config.vin,
        refresh_wait_s=config.refresh_wait_s,
    )
    notifier = Notifier(config.ntfy_url, config.ntfy_topic)
    watcher = ThresholdWatcher(
        threshold=config.charge_target_pct,
        hysteresis=config.hysteresis_pct,
        cooldown_minutes=config.cooldown_minutes,
        renotify_minutes=config.renotify_minutes,
        direction="above",
    )

    log.info("Verbinde mit NissanConnect Services ...")
    await leaf.connect()
    log.info("Verbunden. Starte Abfrage alle %ss.", config.poll_interval_s)

    try:
        while True:
            reading = await leaf.read()
            log.info(
                "Ladestand=%s%% Lädt=%s Angesteckt=%s",
                f"{reading.battery_level_pct:.0f}" if reading.battery_level_pct is not None else "n/a",
                reading.charging,
                reading.plugged_in,
            )

            if reading.battery_level_pct is not None and not debug:
                if watcher.evaluate(reading.battery_level_pct):
                    log.info("Sende Benachrichtigung: Ladestand erreicht")
                    notifier.send(
                        "🔌 Ladestand erreicht",
                        f"Der Nissan Leaf hat {reading.battery_level_pct:.0f} % Ladestand erreicht.",
                    )

            await asyncio.sleep(config.poll_interval_s)
    finally:
        await leaf.close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Nissan Leaf Push Messages")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Nur Messwerte loggen, keine Push-Nachrichten senden.",
    )
    args = parser.parse_args()
    asyncio.run(run(debug=args.debug))


if __name__ == "__main__":
    main()
