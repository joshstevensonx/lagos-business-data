from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from lagosdata.config import Config, load_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name', ['magazine.yaml', 'delivery.yaml'])
def test_shipped_configs_validate(name):
    cfg, reg, _ = load_config(ROOT / 'config' / name)
    # Josh opted in to the free tier (Oct 2026): the shipped configs enable it, but the key
    # lives only in the environment, and the code default stays off
    assert 'AIza' not in (ROOT / 'config' / name).read_text()
    from lagosdata.config import PlacesApiCfg
    assert PlacesApiCfg().enabled is False


def test_typo_is_an_error_not_a_default():
    d = yaml.safe_load((ROOT / 'config' / 'magazine.yaml').read_text())
    d['sources']['gmaps_browser']['concurency'] = 5
    with pytest.raises(ValidationError, match='concurency'):
        Config.model_validate(d)


def test_concurrency_hard_cap():
    d = yaml.safe_load((ROOT / 'config' / 'magazine.yaml').read_text())
    d['sources']['gmaps_browser']['concurrency'] = 7
    with pytest.raises(ValidationError):
        Config.model_validate(d)


def test_bands_are_not_retunable_by_config():
    d = yaml.safe_load((ROOT / 'config' / 'delivery.yaml').read_text())
    d['delivery_scoring']['bands']['hot'] = 55
    with pytest.raises(ValidationError):
        Config.model_validate(d)


def test_no_api_key_field_in_config():
    d = yaml.safe_load((ROOT / 'config' / 'magazine.yaml').read_text())
    d['sources']['places_api']['api_key'] = 'x'
    with pytest.raises(ValidationError):
        Config.model_validate(d)
