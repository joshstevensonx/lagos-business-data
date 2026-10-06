"""Pydantic config models (SPEC §8).

Unknown keys are an error, not a warning: a typo'd `concurency` that silently
defaults is a four-hour mistake.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


# ---------------------------------------------------------------- areas ----
class Corridor(Strict):
    from_: tuple[float, float] = Field(alias='from')
    to: tuple[float, float]
    width_km: float

    model_config = ConfigDict(extra='forbid', populate_by_name=True)


class AreaDef(Strict):
    lat: Optional[float] = None
    lng: Optional[float] = None
    radius_km: Optional[float] = None
    corridor: Optional[Corridor] = None
    polygon: Optional[list[tuple[float, float]]] = None
    aliases: list[str] = []
    derived_from: Optional[str] = None
    low_confidence: bool = False

    @model_validator(mode='after')
    def _one_geometry(self):
        has_disc = self.lat is not None and self.lng is not None and self.radius_km is not None
        n = sum([has_disc, self.corridor is not None, self.polygon is not None])
        if n > 1:
            raise ValueError('an area takes one geometry: lat/lng/radius_km, corridor, or polygon')
        if (self.lat is None) != (self.lng is None):
            raise ValueError('lat and lng go together')
        return self

    @property
    def has_geometry(self) -> bool:
        return (self.radius_km is not None and self.lat is not None) or bool(self.corridor) or bool(self.polygon)


class AreaRegistry(Strict):
    areas: dict[str, AreaDef]


# -------------------------------------------------------------- sources ----
class PlacesApiCfg(Strict):
    enabled: bool = False
    monthly_ceiling_pct: int = Field(80, ge=1, le=100)
    skus: list[Literal['essentials', 'pro', 'enterprise']] = ['essentials']
    top_n: int = 100


class OsmCfg(Strict):
    enabled: bool = True
    via_browser: bool = False
    bbox_pad_km: float = 2.0
    bbox: Optional[tuple[float, float, float, float]] = None   # (south, west, north, east) override
    timeout_seconds: int = 90


class Sweep(Strict):
    center: tuple[float, float]
    zoom: int = 14
    covers: list[str] = []


class GmapsBrowserCfg(Strict):
    enabled: bool = True
    concurrency: int = Field(3, ge=1, le=6)
    zoom: int = 14
    sweeps: list[Sweep] = []
    top_ups: dict[str, int] = {}
    delay_seconds: tuple[float, float] = (2, 6)
    max_searches: int = 400
    max_runtime_minutes: int = 240

    @field_validator('delay_seconds')
    @classmethod
    def _polite_delay(cls, v):
        # volume stays modest by construction: the answer to blocking is to run slower
        if v[0] < 1 or v[1] < v[0]:
            raise ValueError('delay_seconds must be [min, max] with min >= 1')
        return v


class DirectoriesCfg(Strict):
    enabled: bool = True
    sites: list[Literal['finelib', 'ngex', 'cybo', 'vconnect', 'businesslist',
                        'nigeriagalleria', 'connectnigeria']] = ['finelib', 'ngex', 'cybo', 'businesslist']
    rate_per_second: float = Field(1.0, gt=0, le=1.0)
    contact_email: str = ''
    businesslist_pages: int = Field(150, ge=0, le=1500)   # all-Lagos list; geo stage keeps the catchment


class SiteContactsCfg(Strict):
    enabled: bool = True
    max_sites: int = 1500
    concurrency: int = Field(5, ge=1, le=10)


class SourcesCfg(Strict):
    places_api: PlacesApiCfg = PlacesApiCfg()
    osm: OsmCfg = OsmCfg()
    gmaps_browser: GmapsBrowserCfg = GmapsBrowserCfg()
    directories: DirectoriesCfg = DirectoriesCfg()
    site_contacts: SiteContactsCfg = SiteContactsCfg()


# ---------------------------------------------------------------- other ----
class TaxonomyCfg(Strict):
    mode: Literal['full_tree', 'subset'] = 'full_tree'
    terms: Optional[list[str]] = None

    @model_validator(mode='after')
    def _subset_needs_terms(self):
        if self.mode == 'subset' and not self.terms:
            raise ValueError('taxonomy.mode=subset needs taxonomy.terms')
        return self


class Bands(Strict):
    hot: float = 60
    warm: float = 40
    cool: float = 25


class DeliveryScoringCfg(Strict):
    enabled: bool = False
    bands: Bands = Bands()
    keep_all: bool = True

    @field_validator('bands')
    @classmethod
    def _approved_bands(cls, v: Bands):
        # the client's approved scheme (SPEC §6.4) - do not retune without asking
        if (v.hot, v.warm, v.cool) != (60, 40, 25):
            raise ValueError('delivery bands are the client-approved 60/40/25; change score.py deliberately, not via config')
        return v


class PlacePagesCfg(Strict):
    enabled: bool = False
    max_place_visits: int = 400
    order_by: Literal['reviews_desc'] = 'reviews_desc'


class EnrichCfg(Strict):
    place_pages: PlacePagesCfg = PlacePagesCfg()


class OutputCfg(Strict):
    dir: str = 'out/'
    workbook: str


class Config(Strict):
    pipeline: Literal['magazine', 'delivery']
    run_id_prefix: str
    areas: list[str]
    core_areas: list[str] = []
    areas_file: str = 'areas.yaml'          # relative to the config file
    taxonomy: TaxonomyCfg = TaxonomyCfg()
    delivery_scoring: DeliveryScoringCfg = DeliveryScoringCfg()
    sources: SourcesCfg = SourcesCfg()
    enrich: EnrichCfg = EnrichCfg()
    output: OutputCfg

    @model_validator(mode='after')
    def _core_subset(self):
        missing = [a for a in self.core_areas if a not in self.areas]
        if missing:
            raise ValueError(f'core_areas not in areas: {missing}')
        return self


def load_config(path: str | Path) -> tuple[Config, AreaRegistry, Path]:
    """Return (config, area registry, config path). Raises on any unknown key."""
    path = Path(path)
    cfg = Config.model_validate(yaml.safe_load(path.read_text()) or {})
    reg = load_areas(path.parent / cfg.areas_file)
    return cfg, reg, path


def load_areas(path: str | Path) -> AreaRegistry:
    path = Path(path)
    if not path.exists():
        return AreaRegistry(areas={})
    return AreaRegistry.model_validate(yaml.safe_load(path.read_text()) or {'areas': {}})
