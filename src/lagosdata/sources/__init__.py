"""Source registry. Sources named in config but not yet built are skipped with a
logged notice rather than silently ignored (SPEC §10 builds them in order)."""
from .osm import OsmSource

IMPLEMENTED = {'osm': OsmSource}

# run order (SPEC §3): later sources fill gaps left by earlier ones
ORDER = ['places_api', 'osm', 'gmaps_browser', 'directories']
