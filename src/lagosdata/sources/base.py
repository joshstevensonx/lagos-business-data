"""Source interface.

A source turns (term, area) searches into raw dicts, which `discover` appends
to raw/<source>.jsonl untouched. `to_business` maps one raw dict onto the
canonical record later, so a mapping fix never needs a re-collection.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..record import Business


@dataclass(frozen=True)
class Search:
    term: str
    area: str            # an area name, a sweep label, or '*' for a whole-bbox query


class SourceUnavailable(Exception):
    """The source cannot be reached at all (network policy, missing dependency).
    Never fatal to a run: discover logs it and moves on."""


class Source(ABC):
    name: str = ''

    def __init__(self, run):
        self.run = run

    @abstractmethod
    def plan(self) -> list[Search]:
        """Every search this source would execute for the run's config."""

    @abstractmethod
    def search(self, s: Search) -> list[dict]:
        """Execute one search, return raw rows. Raise SourceUnavailable or any error on failure."""

    @abstractmethod
    def to_business(self, raw: dict) -> Business | None:
        """Map one raw row to a Business, or None to drop it (log why in the row)."""
