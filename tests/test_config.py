from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from lagosdata.config import Config, load_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name', ['magazine.yaml', 'delivery.yaml'])
def test_shipped_configs_validate(name):
    cfg, reg, _ = load_config(ROOT / 'config' / name)
    assert cfg.sources.places_api.enabled is False        # off by default, must stay that way


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
