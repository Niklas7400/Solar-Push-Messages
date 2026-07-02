import argparse
import asyncio
import logging
from datetime import datetime

from solar_push.config import Config, load_config
from solar_push.inverter import Inverter
from solar_push.logic import Evaluator
from solar_push.notifier import Notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("solar_push")


def _build_inverter(config: Config):
    if config.data_source == "cloud":
        from solar_push.cloud_inverter import CloudInverter

        return CloudInverter(
            username=config.fusion_username,
            password=config.fusion_password,
            subdomain=config.fusion_subdomain,
            plant_id=config.fusion_plant_id,
            grid_export_positive=config.grid_export_positive,
        )
    return Inverter(
        host=config.inverter_host,
        port=config.inverter_port,
        slave_id=config.inverter_slave_id,
        grid_export_positive=config.grid_export_positive,
    )


async def run(debug: bool) -> None:
    config = load_config()
    inverter = _build_inverter(config)
    notifier = Notifier(config.ntfy_url, config.ntfy_topic)
    evaluator = Evaluator(
        increase_threshold_w=config.increase_threshold_w,
        decrease_threshold_w=config.decrease_threshold_w,
        hysteresis_w=config.hysteresis_w,
        cooldown_minutes=config.cooldown_minutes,
        renotify_minutes=config.renotify_minutes,
    )

    if config.data_source == "cloud":
        log.info("Verbinde mit FusionSolar Cloud (%s) ...", config.fusion_subdomain)
    else:
        log.info("Verbinde mit Wechselrichter %s:%s ...", config.inverter_host, config.inverter_port)
    await inverter.connect()
    log.info("Verbunden. Starte Abfrage alle %ss.", config.poll_interval_s)

    try:
        while True:
            reading = await inverter.read()
            log.info(
                "PV=%.0fW Grid=%s Batterie=%s%%",
                reading.pv_power_w,
                f"{reading.grid_power_w:.0f}W" if reading.grid_power_w is not None else "n/a",
                f"{reading.battery_soc_pct:.0f}" if reading.battery_soc_pct is not None else "n/a",
            )

            if reading.grid_power_w is None:
                log.warning(
                    "Kein Netz-Leistungsmesswert verfügbar (kein Smart Power Sensor "
                    "am Wechselrichter?). Benachrichtigungen sind ohne diesen Wert "
                    "nicht möglich."
                )
            elif not debug:
                decision = evaluator.evaluate(reading.grid_power_w, now=datetime.now())
                if decision.should_notify:
                    log.info("Sende Benachrichtigung: %s", decision.title)
                    notifier.send(decision.title, decision.message)

            await asyncio.sleep(config.poll_interval_s)
    finally:
        await inverter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Solar Push Messages")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Nur Messwerte loggen, keine Push-Nachrichten senden (zum Kalibrieren).",
    )
    args = parser.parse_args()
    asyncio.run(run(debug=args.debug))


if __name__ == "__main__":
    main()
