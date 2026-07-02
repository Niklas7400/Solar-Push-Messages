import os

import pytest

from solar_push.config import load_config

BASE_ENV = {
    "DATA_SOURCE": "cloud",
    "FUSIONSOLAR_USERNAME": "user",
    "FUSIONSOLAR_PASSWORD": "pass",
    "NTFY_TOPIC": "topic",
}


@pytest.fixture
def clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith(("DATA_SOURCE", "INVERTER_", "FUSIONSOLAR_", "NTFY_")):
            monkeypatch.delenv(key, raising=False)
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    yield monkeypatch


def test_empty_optional_env_vars_are_treated_as_unset(clean_env):
    # A .env line like "FUSIONSOLAR_PLANT_ID=" sets the var to an empty
    # string, not unset - load_config must not mistake "" for a real value.
    clean_env.setenv("FUSIONSOLAR_PLANT_ID", "")
    config = load_config()
    assert config.fusion_plant_id is None


def test_set_plant_id_is_kept(clean_env):
    clean_env.setenv("FUSIONSOLAR_PLANT_ID", "NE=12345")
    config = load_config()
    assert config.fusion_plant_id == "NE=12345"


def test_cloud_requires_credentials(clean_env):
    clean_env.delenv("FUSIONSOLAR_PASSWORD")
    with pytest.raises(ValueError):
        load_config()
