"""The one canonical record that flows through every stage (SPEC §7).

On disk it is plain JSON. Absent strings are '' - never None - so the workbook
writes blanks rather than the text "None".
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

OUTSIDE = 'Outside catchment'
UNASSIGNED = 'Unassigned'
CORE_ZONE = 'Core catchment'
RING_ZONE = 'Ring area'
UNCLASSIFIED = ('Other Local Services', 'Unclassified (needs review)')

# the six channels counted in contact_channels (matches reference/score.py)
CHANNEL_FIELDS = ('phone', 'website', 'email', 'instagram', 'facebook', 'linkedin')


@dataclass
class Business:
    # identity
    name: str
    place_id: str = ''
    # location
    area: str = ''                  # assigned catchment, or 'Outside catchment' / 'Unassigned'
    zone: str = ''                  # 'Core catchment' | 'Ring area' (or the OUTSIDE/UNASSIGNED marker)
    street: str = ''
    addr: str = ''
    lat: float | str = ''
    lng: float | str = ''
    # classification
    group: str = ''                 # 1 of 29
    sub: str = ''                   # 1 of 436
    legacy18: str = ''              # legacy 18-category column
    label: str = ''                 # raw source category string, kept for re-classification
    # contact
    phone: str = ''                 # +234XXXXXXXXXX
    phones_all: str = ''            # '; '-joined
    whatsapp: str = ''
    website: str = ''
    email: str = ''
    instagram: str = ''
    facebook: str = ''
    twitter: str = ''
    linkedin: str = ''
    tiktok: str = ''
    contact_channels: int = 0
    # signals
    rating: float | str = ''
    reviews: int | str = ''
    additional_info: dict = field(default_factory=dict)   # NESTED shape, see SPEC §6.4
    delivery_text_signals: list = field(default_factory=list)
    # magazine pipeline
    priority: str = ''
    package: str = ''
    contactable: str = ''
    verification: str = ''
    sales_status: str = 'Not Contacted'
    notes: str = ''
    # delivery pipeline
    score: float | str = ''
    band: str = ''
    score_components: dict = field(default_factory=dict)
    score_basis: str = ''           # 'Full' | 'Floor - not enriched'
    delivery_category: str = ''
    # provenance
    source: str = ''
    sources_all: list = field(default_factory=list)
    maps: str = ''
    added: str = ''                 # ISO date
    conflicts: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'Business':
        names = {f.name for f in dataclasses.fields(cls)}
        unknown = set(d) - names
        if unknown:
            raise ValueError(f'unknown Business fields: {sorted(unknown)}')
        kw = {k: ('' if v is None and k not in _NON_STR else v) for k, v in d.items()}
        return cls(**kw)


_NON_STR = {'additional_info', 'delivery_text_signals', 'score_components', 'sources_all',
            'conflicts', 'contact_channels'}


def count_channels(b: Business) -> int:
    return sum(1 for f in CHANNEL_FIELDS if getattr(b, f))


# source trust, highest first (SPEC §6.3). Matched against the `source` string.
TRUST_ORDER = [
    ('places_api', ('places api',)),
    ('gmaps', ('google maps',)),
    ('osm', ('openstreetmap',)),
    ('directory', ('finelib', 'ngex', 'cybo', 'vconnect', 'businesslist', 'directory',
                   'nigeriagalleria', 'connectnigeria', 'legacy seed')),
    ('manual', ('csv', 'manual')),
]


def source_kind(source: str) -> str:
    s = (source or '').lower()
    for kind, needles in TRUST_ORDER:
        if any(n in s for n in needles):
            return kind
    return 'manual'


def trust(source: str) -> int:
    """Higher is more trusted."""
    kinds = [k for k, _ in TRUST_ORDER]
    return len(kinds) - kinds.index(source_kind(source))


def is_google(b: Business) -> bool:
    return any(source_kind(s) in ('places_api', 'gmaps') for s in (b.sources_all or [b.source]))
