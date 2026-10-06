"""Source registry. Sources named in config but not yet built are skipped with a
logged notice rather than silently ignored (SPEC §10 builds them in order)."""
from .csv_import import CsvImportSource
from .directories import DirectoriesSource
from .gmaps_browser import GmapsBrowserSource
from .osm import OsmSource

IMPLEMENTED = {'osm': OsmSource, 'gmaps_browser': GmapsBrowserSource, 'manual_csv': CsvImportSource,
               'directories': DirectoriesSource}

# run order (SPEC §3): later sources fill gaps left by earlier ones
ORDER = ['osm', 'gmaps_browser', 'directories']   # places_api is an enricher (SPEC §3.1: not for discovery)
