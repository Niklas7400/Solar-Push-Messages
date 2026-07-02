"""Dump raw FusionSolar cloud API data for inspection.

Run this locally with FUSIONSOLAR_USERNAME/FUSIONSOLAR_PASSWORD set in your
.env (never pass them as command-line arguments or paste them into chat -
this script reads them from the environment so the plaintext password stays
on your machine). Share the printed JSON (redact serial numbers/plant names
if you like, the field *names* are what matters) so the grid-power parsing
in solar_push/cloud_inverter.py can be verified against a real account.

Usage: python scripts/dump_fusion_solar_flow.py
"""

import json
import os

from dotenv import load_dotenv
from fusion_solar_py.client import FusionSolarClient

load_dotenv()


def main() -> None:
    username = os.environ["FUSIONSOLAR_USERNAME"]
    password = os.environ["FUSIONSOLAR_PASSWORD"]
    subdomain = os.getenv("FUSIONSOLAR_SUBDOMAIN", "region01eu5")

    client = FusionSolarClient(username, password, huawei_subdomain=subdomain)

    plant_ids = client.get_plant_ids()
    print(f"Plant IDs: {plant_ids}\n")
    plant_id = os.getenv("FUSIONSOLAR_PLANT_ID") or plant_ids[0]

    print("=== get_power_status() ===")
    print(client.get_power_status())

    print("\n=== get_plant_flow() ===")
    flow = client.get_plant_flow(plant_id)
    print(json.dumps(flow, indent=2, ensure_ascii=False))

    print("\n=== get_battery_ids() ===")
    try:
        battery_ids = client.get_battery_ids(plant_id)
        print(battery_ids)
        if battery_ids:
            print("\n=== get_battery_basic_stats() ===")
            print(client.get_battery_basic_stats(battery_ids[0]))
    except Exception as exc:
        print(f"No battery / failed to read: {exc}")

    client.log_out()


if __name__ == "__main__":
    main()
