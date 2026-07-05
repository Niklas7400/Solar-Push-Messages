import argparse
import asyncio
import logging
from datetime import datetime

from solar_push.config import Config, load_config
from solar_push.daily_summary import DailyEnergyTracker
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
            battery_charge_positive=config.battery_charge_positive,
        )
    return Inverter(
        host=config.inverter_host,
        port=config.inverter_port,
        slave_id=config.inverter_slave_id,
        grid_export_positive=config.grid_export_positive,
        battery_charge_positive=config.battery_charge_positive,
    )


async def run(debug: bool) -> None:
    config = load_config()
    inverter = _build_inverter(config)
    notifier = Notifier(config.ntfy_url, config.ntfy_topic)
    evaluator = Evaluator(
        increase_threshold_w=config.increase_threshold_w,
        decrease_threshold_w=config.decrease_threshold_w,
        hysteresis_w=config.hysteresis_w,
        battery_low_soc_pct=config.battery_low_soc_pct,
        battery_low_hysteresis_pct=config.battery_low_hysteresis_pct,
        grid_import_alert_w=config.grid_import_alert_w,
        grid_import_alert_min_pv_w=config.grid_import_alert_min_pv_w,
        cooldown_minutes=config.cooldown_minutes,
        renotify_minutes=config.renotify_minutes,
    )
    daily_tracker = DailyEnergyTracker(config.daily_summary_hour) if config.daily_summary_enabled else None

    if config.data_source == "cloud":
        log.info("Verbinde mit FusionSolar Cloud (%s) ...", config.fusion_subdomain)
    else:
        log.info("Verbinde mit Wechselrichter %s:%s ...", config.inverter_host, config.inverter_port)
    await inverter.connect()
    log.info("Verbunden. Starte Abfrage alle %ss.", config.poll_interval_s)

    consecutive_failures = 0
    max_consecutive_failures = 3

    try:
        while True:
            try:
                reading = await inverter.read()
                consecutive_failures = 0
                log.info(
                    "PV=%.0fW Grid=%s Batterie=%s%% Speicherleistung=%s",
                    reading.pv_power_w,
                    f"{reading.grid_power_w:.0f}W" if reading.grid_power_w is not None else "n/a",
                    f"{reading.battery_soc_pct:.0f}" if reading.battery_soc_pct is not None else "n/a",
                    f"{reading.battery_discharge_w:.0f}W" if reading.battery_discharge_w is not None else "n/a",
                )

                if reading.grid_power_w is None and reading.battery_discharge_w is None:
                    log.warning(
                        "Weder Netz- noch Speicher-Leistungsmesswert verfügbar. "
                        "Benachrichtigungen sind ohne mindestens einen davon nicht möglich."
                    )

                now = datetime.now()
                if daily_tracker is not None:
                    daily_tracker.add(reading.pv_power_w, reading.grid_power_w, config.poll_interval_s, now)

                if not debug:
                    decisions = evaluator.evaluate(
                        grid_power_w=reading.grid_power_w,
                        battery_discharge_w=reading.battery_discharge_w,
                        battery_soc_pct=reading.battery_soc_pct,
                        pv_power_w=reading.pv_power_w,
                        now=now,
                    )
                    if daily_tracker is not None:
                        summary = daily_tracker.maybe_build_summary(now)
                        if summary is not None:
                            decisions.append(summary)

                    for decision in decisions:
                        log.info("Sende Benachrichtigung: %s", decision.title)
                        notifier.send(decision.title, decision.message, priority=decision.priority)
            except Exception:
                consecutive_failures += 1
                log.exception(
                    "Fehler in diesem Abfragezyklus (%d in Folge), überspringe und versuche es beim "
                    "nächsten Intervall erneut",
                    consecutive_failures,
                )
                if consecutive_failures >= max_consecutive_failures:
                    log.warning(
                        "%d Fehlversuche in Folge, versuche komplette Neuverbindung", consecutive_failures
                    )
                    try:
                        await inverter.close()
                    except Exception:
                        log.debug("Fehler beim Schließen vor Neuverbindung", exc_info=True)
                    try:
                        await inverter.connect()
                        log.info("Neuverbindung erfolgreich")
                        consecutive_failures = 0
                    except Exception:
                        log.exception("Neuverbindung fehlgeschlagen, versuche es beim nächsten Intervall erneut")

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
