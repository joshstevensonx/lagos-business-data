import json
import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / 'fixtures'


@pytest.fixture
def overpass_fixture():
    return json.loads((FIX / 'overpass-magazine-synthetic.json').read_text())


@pytest.fixture
def magazine_run(tmp_path, overpass_fixture):
    """A Run on the shipped magazine config whose OSM transport returns the fixture."""
    from lagosdata.config import load_config
    from lagosdata.run import Run
    cfg, areas, path = load_config(ROOT / 'config' / 'magazine.yaml')
    run = Run.create(cfg, areas, path, run_id='test-magazine', out_dir=str(tmp_path), echo=False)
    run.options['source_kwargs'] = {'osm': {'transport': lambda q: overpass_fixture}}
    run.cfg.sources.gmaps_browser.enabled = False      # tests never touch live Google Maps
    yield run
    run.close()


requires_soffice = pytest.mark.skipif(not (shutil.which('soffice') or shutil.which('libreoffice')),
                                      reason='LibreOffice not installed')


# the cloud container ships Chromium at a fixed path that may not match the installed playwright's build
if not os.environ.get('LAGOSDATA_CHROMIUM') and os.path.exists('/opt/pw-browsers/chromium'):
    os.environ['LAGOSDATA_CHROMIUM'] = '/opt/pw-browsers/chromium'


def _has_playwright():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


requires_playwright = pytest.mark.skipif(not _has_playwright(), reason='playwright not installed')
