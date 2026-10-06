"""SPEC §5 guardrail: the catch-all must hold < 5% of a recorded sample of real labels."""
import collections
import json
from pathlib import Path

from lagosdata.classify import classify
from lagosdata.record import UNCLASSIFIED
from lagosdata.taxonomy import normalise
from lagosdata.tree import ALL_SUBS, ALL_TERMS, GROUPS

FIX = Path(__file__).parent / 'fixtures' / 'labels_v3_2026-09.json'


def test_tree_shape():
    assert len(GROUPS) == 29
    assert len(ALL_SUBS) == 436
    assert len(ALL_TERMS) == 321


def test_unclassified_under_five_percent():
    sample = json.loads(FIX.read_text())          # (label, name) from the delivered v3 workbook
    assert len(sample) > 4000
    unc = [(lab, name) for lab, name in sample if classify(lab, name) == UNCLASSIFIED]
    share = len(unc) / len(sample)
    top = collections.Counter(lab or '(no label)' for lab, _ in unc).most_common(20)
    assert share < 0.05, f'unclassified {share:.1%} - top labels to write rules for:\n' + \
        '\n'.join(f'  {n:>4}  {lab}' for lab, n in top)


def test_every_rule_output_is_in_the_tree():
    from lagosdata.classify import RULES
    subs = set(ALL_SUBS)
    assert [(g, s) for g, s, _ in RULES if (g, s) not in subs] == []


def test_first_match_wins_and_known_outputs():
    assert classify('Pharmacy', 'Medplus') == ('Health & Medical', 'Pharmacies')
    assert classify('Barber shop', 'Prince Barbing') == ('Beauty & Personal Care', 'Barbers')
    assert classify('', '') == UNCLASSIFIED
    # slash is treated as a separator
    assert classify('Bar/Lounge', '')[0] == 'Bars & Entertainment'


def test_legacy18_blob_prechecks():
    assert normalise('Hair salon', 'Kings Barbing Saloon') == 'Barbers'
