# -*- coding: utf-8 -*-
"""Magazine census workbook - 8 tabs (SPEC §1.1).

Ported from reference/build_magazine_workbook.py: same tabs, fonts, colours,
live COUNTIFS, freeze panes, autofilter and dropdowns. Changes:
  * areas / core areas come from config, not constants
  * formulas address columns by header name (Cols), never by typed letter
  * 'Outside catchment' and 'Unassigned' records stay in MASTER DATABASE and get
    their own rows, but are excluded from headline core/ring counts
  * README and SOURCE LOG are generated from the run, not hand-written
  * returns `meta` (where every KPI lives) so verify can recount each one
"""
from __future__ import annotations

import collections

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from ..record import CORE_ZONE, OUTSIDE, RING_ZONE, UNASSIGNED, source_kind
from ..tree import TREE
from .style import (FONT, GOLD, GREY, LIGHT, NAVY, Cols, blank, body, bold, box, center, fill,
                    kpi_font, sect_fill, sect_font, style_header, style_total_row, sub_font, title_font,
                    widths, write_readme)

MD = "'MASTER DATABASE'"
COLS = ['ID', 'Business Name', 'Zone', 'Catchment', 'Street / Cluster', 'Category Group', 'Subcategory',
        'Source Category', 'Legacy 18-Category', 'Full Address', 'Phone', 'Website', 'Google Maps',
        'Google Rating', 'Google Reviews', 'Has Phone', 'Latitude', 'Longitude', 'Data Source',
        'Date Added', 'Last Checked', 'Verification', 'Prospect Priority', 'Suggested Package',
        'Sales Status', 'Sales Notes',
        # appended after the delivered v3 layout so the client's familiar columns do not move
        'WhatsApp', 'Email', 'Instagram', 'Facebook', 'Contact Channels', 'All Sources',
        # delivery prospecting (filled where the record was scored by the delivery pipeline)
        'Programme', 'Delivery Category', 'Delivery Score', 'Delivery Band', 'Score Basis']
SALES = 'Not Contacted,Contacted,Meeting Booked,Proposal Sent,Won,Declined,Do Not Contact'
PRIORITY_A = 'A - High commercial relevance'
PRIORITY_B = 'B - Potential advertiser'
PRIORITY_C = 'C - Ring area, contactable'


MAGAZINE_AREAS = ['Anthony / Anthony Village', 'Maryland / Mende', 'Ilupeju', 'Gbagada', 'Obanikoro',
                  'Palmgrove', 'Ojota']


def programme(area: str, areas: list[str]) -> str:
    if area in MAGAZINE_AREAS:
        return 'Magazine catchment'
    if area in areas:
        return 'Delivery area'
    return ''


def _num(v, cast):
    try:
        return cast(v) if str(v).strip() not in ('', 'None') else None
    except Exception:
        return None


def build(recs, cfg, searches, info) -> tuple[Workbook, dict]:
    N = len(recs)
    LAST = max(N + 1, 2)
    TODAY = info['today']
    CORE = list(cfg.core_areas)
    RING = [a for a in cfg.areas if a not in CORE]
    AREAS = CORE + RING
    EXTRA = [OUTSIDE, UNASSIGNED]
    GROUPS = list(dict.fromkeys(list(TREE.keys()) + ['Other Local Services']))
    C = Cols(COLS)
    meta = {'pipeline': 'magazine', 'rows': N, 'kpis': [], 'group_table': [], 'checks': {}}
    wb = Workbook()

    def R(h):  # absolute MASTER DATABASE range for a header
        return C.rng(MD, h, LAST)

    # ============================== MASTER DATABASE ==========================
    ws = wb.create_sheet('MASTER DATABASE')
    for i, h in enumerate(COLS, start=1): ws.cell(row=1, column=i, value=h)
    style_header(ws, 1, len(COLS))
    prio_fills = {'A': ('C6EFCE', '006100'), 'B': (GOLD, '7F6000'), 'C': ('FCE4D6', '833C0B'), 'D': (GREY, '595959')}
    wrap_cols = (C.n('Full Address'), C.n('Sales Notes'))
    for i, r in enumerate(recs):
        rr = i + 2
        vals = [i + 1, r.name, r.zone, r.area, r.street, r.group, r.sub, r.label, r.legacy18, r.addr,
                r.phone, r.website, r.maps, _num(r.rating, float), _num(r.reviews, int), r.contactable,
                _num(r.lat, float), _num(r.lng, float), r.source, r.added, TODAY, r.verification,
                r.priority, r.package, r.sales_status, r.notes,
                r.whatsapp, r.email, r.instagram, r.facebook, r.contact_channels,
                '; '.join(r.sources_all),
                programme(r.area, CORE + RING), r.delivery_category, r.score, r.band, r.score_basis]
        for c, v in enumerate(vals, start=1):
            cell = ws.cell(row=rr, column=c, value=blank(v))
            cell.font = body
            cell.alignment = Alignment(vertical='top', wrap_text=(c in wrap_cols))
        ws.cell(row=rr, column=C.n('Google Rating')).number_format = '0.0'
        ws.cell(row=rr, column=C.n('Google Reviews')).number_format = '#,##0'
        ws.cell(row=rr, column=C.n('Latitude')).number_format = '0.000000'
        ws.cell(row=rr, column=C.n('Longitude')).number_format = '0.000000'
        p0 = (r.priority or 'D')[:1]
        f, col = prio_fills.get(p0, prio_fills['D'])
        pr = ws.cell(row=rr, column=C.n('Prospect Priority'))
        pr.fill = fill(f)
        pr.font = Font(name=FONT, size=10, color=col, bold=(p0 == 'A'))
        if r.zone == CORE_ZONE:
            ws.cell(row=rr, column=C.n('Zone')).font = Font(name=FONT, size=10, bold=True, color=NAVY)
    widths(ws, [6, 38, 15, 26, 26, 26, 26, 26, 20, 44, 17, 26, 30, 9, 10, 9, 12, 12, 28, 12, 12, 20, 30, 14,
                16, 28, 17, 28, 24, 24, 10, 36, 20, 20, 10, 28, 20])
    ws.freeze_panes = 'C2'
    ws.auto_filter.ref = f'A1:{get_column_letter(len(COLS))}{LAST}'
    dv_area = DataValidation(type='list', formula1='"' + ','.join(AREAS + EXTRA) + '"', allow_blank=True)
    dv_sale = DataValidation(type='list', formula1=f'"{SALES}"', allow_blank=True)
    dv_pkg = DataValidation(type='list', formula1='"Premium,Standard,Listing"', allow_blank=True)
    for dv, h in ((dv_area, 'Catchment'), (dv_sale, 'Sales Status'), (dv_pkg, 'Suggested Package')):
        ws.add_data_validation(dv); dv.add(f'{C[h]}2:{C[h]}{LAST}')

    # ============================== DASHBOARD ================================
    ws = wb.create_sheet('DASHBOARD', 0)
    ws.sheet_view.showGridLines = False
    ws['A1'] = info.get('title') or f'ANTHONY COMMUNITY MEDIA - BUSINESS DATABASE ({info["run_id"]})'
    ws['A1'].font = title_font
    ws['A2'] = (f'{len(AREAS)} catchments  |  {len(TREE)} category groups  |  '
                f'{sum(len(d["subs"]) for d in TREE.values())}-subcategory tree  |  Last refreshed {TODAY}')
    ws['A2'].font = sub_font
    ws.merge_cells('A1:G1'); ws.merge_cells('A2:G2')
    ws['A4'] = 'HEADLINE NUMBERS'; ws['A4'].font = sect_font; ws['A4'].fill = sect_fill
    ws.merge_cells('A4:G4')
    core_names = ' + '.join(a.split('/')[0].strip() for a in CORE) or 'none configured'
    kpis = [
        ('total', 'Total businesses in database (all zones)', f'=COUNTA({C.rng(MD, "Business Name", LAST, False)})'),
        ('core', f'Core catchment ({core_names})', f'=COUNTIF({R("Zone")},"{CORE_ZONE}")'),
        ('ring', info.get('ring_label') or f'Ring areas ({len(RING)} surrounding)', f'=COUNTIF({R("Zone")},"{RING_ZONE}")'),
        ('outside', 'Outside catchment (expansion leads - not in headline counts)', f'=COUNTIF({R("Zone")},"{OUTSIDE}")'),
        ('unassigned', 'Unassigned (no coordinates, area not in address)', f'=COUNTIF({R("Zone")},"{UNASSIGNED}")'),
        ('phone', 'With a phone number', f'=COUNTIF({R("Has Phone")},"Yes")'),
        ('google_verified', 'Google-verified location', f'=COUNTIF({R("Verification")},"Google-verified")'),
        ('prio_a', 'Priority A prospects (core, contactable, visible)', f'=COUNTIF({R("Prospect Priority")},"{PRIORITY_A}")'),
        ('prio_b', 'Priority B prospects', f'=COUNTIF({R("Prospect Priority")},"{PRIORITY_B}")'),
        ('prio_c', 'Priority C prospects (ring area, contactable)', f'=COUNTIF({R("Prospect Priority")},"{PRIORITY_C}")'),
        ('cross_verified', 'Cross-verified in more than one source', f'=COUNTIF({R("Data Source")},"Multiple sources (cross-verified)")'),
    ]
    r0 = 5
    for i, (key, lab, f) in enumerate(kpis):
        ws.cell(row=r0 + i, column=1, value=lab).font = bold
        c = ws.cell(row=r0 + i, column=4, value=f)
        c.font = kpi_font; c.alignment = Alignment(horizontal='right'); c.number_format = '#,##0'
        ws.cell(row=r0 + i, column=1).border = box; c.border = box
        meta['kpis'].append({'key': key, 'label': lab, 'sheet': 'DASHBOARD', 'cell': f'D{r0 + i}', 'formula': f})

    gr = r0 + len(kpis) + 1
    ws.cell(row=gr, column=1, value='BUSINESSES BY CATEGORY GROUP (core + ring only)').font = sect_font
    ws.cell(row=gr, column=1).fill = sect_fill
    ws.merge_cells(start_row=gr, start_column=1, end_row=gr, end_column=7)
    hdr = ['Category Group', 'Core catchment', 'Ring areas', 'Total', 'With phone', 'Priority A', '% of total']
    for i, h in enumerate(hdr, start=1): ws.cell(row=gr + 1, column=i, value=h)
    style_header(ws, gr + 1, 7)
    first = gr + 2
    tot = first + len(GROUPS)
    G, Z, P, PR = R('Category Group'), R('Zone'), R('Has Phone'), R('Prospect Priority')
    for i, g in enumerate(GROUPS):
        rr = first + i
        ws.cell(row=rr, column=1, value=g).font = bold
        ws.cell(row=rr, column=2, value=f'=COUNTIFS({Z},"{CORE_ZONE}",{G},$A{rr})')
        ws.cell(row=rr, column=3, value=f'=COUNTIFS({Z},"{RING_ZONE}",{G},$A{rr})')
        ws.cell(row=rr, column=4, value=f'=SUM(B{rr}:C{rr})')
        ws.cell(row=rr, column=5, value=f'=COUNTIFS({G},$A{rr},{P},"Yes",{Z},"<>{OUTSIDE}",{Z},"<>{UNASSIGNED}")')
        ws.cell(row=rr, column=6, value=f'=COUNTIFS({G},$A{rr},{PR},"{PRIORITY_A}")')
        p = ws.cell(row=rr, column=7, value=f'=IFERROR(D{rr}/$D${tot},0)'); p.number_format = '0.0%'
        for c in range(1, 8):
            cell = ws.cell(row=rr, column=c); cell.border = box
            if c > 1: cell.font = body; cell.alignment = center
            if i % 2: cell.fill = fill(GREY)
        meta['group_table'].append({'group': g, 'row': rr})
    ws.cell(row=tot, column=1, value='TOTAL')
    for c in range(2, 7):
        L = get_column_letter(c)
        ws.cell(row=tot, column=c, value=f'=SUM({L}{first}:{L}{tot - 1})')
    ws.cell(row=tot, column=7, value=f'=IFERROR(D{tot}/$D${tot},0)').number_format = '0.0%'
    style_total_row(ws, tot, 7)
    meta['group_table_cols'] = {'core': 'B', 'ring': 'C', 'total': 'D', 'phone': 'E', 'prio_a': 'F'}
    meta['group_table_total_row'] = tot
    note = tot + 2
    ws.cell(row=note, column=1, value='Note').font = bold
    ws.cell(row=note, column=2, value='Every figure here is a live formula over MASTER DATABASE. Add or edit rows '
            'there and this updates automatically.').font = sub_font
    ws.merge_cells(start_row=note, start_column=2, end_row=note, end_column=7)
    widths(ws, [52, 16, 16, 12, 12, 12, 14])
    ws.freeze_panes = 'A5'

    # ============================== AREA SUMMARY =============================
    ws = wb.create_sheet('AREA SUMMARY')
    ws.sheet_view.showGridLines = False
    ws['A1'] = 'COVERAGE BY CATCHMENT'; ws['A1'].font = title_font; ws.merge_cells('A1:I1')
    hdr = ['Catchment', 'Zone', 'Businesses', '% of database', 'With phone', 'Google-verified', 'Priority A',
           'Priority B', 'Priority C/D']
    for i, h in enumerate(hdr, start=1): ws.cell(row=3, column=i, value=h)
    style_header(ws, 3, len(hdr))
    A, V = R('Catchment'), R('Verification')
    rows = AREAS + EXTRA
    tr = 4 + len(rows)
    for i, a in enumerate(rows):
        rr = 4 + i
        ws.cell(row=rr, column=1, value=a).font = bold
        ws.cell(row=rr, column=2, value=CORE_ZONE if a in CORE else (RING_ZONE if a in RING else a))
        ws.cell(row=rr, column=3, value=f'=COUNTIF({A},$A{rr})')
        ws.cell(row=rr, column=4, value=f'=IFERROR(C{rr}/$C${tr},0)').number_format = '0.0%'
        ws.cell(row=rr, column=5, value=f'=COUNTIFS({A},$A{rr},{P},"Yes")')
        ws.cell(row=rr, column=6, value=f'=COUNTIFS({A},$A{rr},{V},"Google-verified")')
        ws.cell(row=rr, column=7, value=f'=COUNTIFS({A},$A{rr},{PR},"{PRIORITY_A}")')
        ws.cell(row=rr, column=8, value=f'=COUNTIFS({A},$A{rr},{PR},"{PRIORITY_B}")')
        ws.cell(row=rr, column=9, value=f'=C{rr}-G{rr}-H{rr}')
        for c in range(1, 10):
            cell = ws.cell(row=rr, column=c); cell.border = box
            if c > 2: cell.font = body; cell.alignment = center
            else: cell.font = bold if c == 1 else body
            if a in CORE: cell.fill = fill(LIGHT)
            elif a in EXTRA: cell.fill = fill(GREY)
    ws.cell(row=tr, column=1, value='TOTAL')
    for c in (3, 5, 6, 7, 8, 9):
        L = get_column_letter(c)
        ws.cell(row=tr, column=c, value=f'=SUM({L}4:{L}{tr - 1})')
    ws.cell(row=tr, column=4, value=f'=IFERROR(C{tr}/$C${tr},0)').number_format = '0.0%'
    style_total_row(ws, tr, 9)
    widths(ws, [28, 18, 12, 14, 12, 16, 12, 12, 14])
    meta['checks']['area_summary_total'] = {'sheet': 'AREA SUMMARY', 'cell': f'C{tr}'}

    # ============================== GROUP x AREA MATRIX ======================
    ws = wb.create_sheet('GROUP x AREA')
    ws.sheet_view.showGridLines = False
    ws['A1'] = 'CATEGORY GROUP BY CATCHMENT'; ws['A1'].font = title_font
    ws.merge_cells('A1:I1')
    hdr = ['Category Group'] + AREAS + EXTRA + ['Total']
    for i, h in enumerate(hdr, start=1): ws.cell(row=3, column=i, value=h)
    style_header(ws, 3, len(hdr))
    tr = 4 + len(GROUPS)
    for i, g in enumerate(GROUPS):
        rr = 4 + i
        ws.cell(row=rr, column=1, value=g).font = bold
        for j in range(len(AREAS + EXTRA)):
            col = 2 + j
            L = get_column_letter(col)
            ws.cell(row=rr, column=col, value=f'=COUNTIFS({G},$A{rr},{A},{L}$3)')
        ws.cell(row=rr, column=len(hdr), value=f'=SUM(B{rr}:{get_column_letter(len(hdr) - 1)}{rr})')
        for c in range(1, len(hdr) + 1):
            cell = ws.cell(row=rr, column=c); cell.border = box
            if c > 1: cell.font = body; cell.alignment = center
            if i % 2: cell.fill = fill(GREY)
    ws.cell(row=tr, column=1, value='TOTAL')
    for c in range(2, len(hdr) + 1):
        L = get_column_letter(c)
        ws.cell(row=tr, column=c, value=f'=SUM({L}4:{L}{tr - 1})')
    style_total_row(ws, tr, len(hdr))
    widths(ws, [30] + [17] * len(AREAS + EXTRA) + [12])
    ws.freeze_panes = 'B4'
    meta['checks']['group_area_total'] = {'sheet': 'GROUP x AREA', 'cell': f'{get_column_letter(len(hdr))}{tr}'}

    # ============================== CATEGORY TREE ============================
    ws = wb.create_sheet('CATEGORY TREE')
    ws.sheet_view.showGridLines = False
    n_subs = sum(len(d['subs']) for d in TREE.values())
    ws['A1'] = f'FULL CATEGORY TREE - {len(TREE)} GROUPS, {n_subs} SUBCATEGORIES'; ws['A1'].font = title_font
    ws['A2'] = ('Every subcategory you specified, with how many businesses landed in it. Zero means nothing '
                'matched yet - that is a research gap, not an error.')
    ws['A2'].font = sub_font
    ws.merge_cells('A1:F1'); ws.merge_cells('A2:F2')
    hdr = ['Category Group', 'Subcategory', 'Found', 'Core catchment', 'Ring areas', 'Status']
    for i, h in enumerate(hdr, start=1): ws.cell(row=4, column=i, value=h)
    style_header(ws, 4, len(hdr))
    row = 5
    S = R('Subcategory')
    tree_rows = [(g, s) for g, d in TREE.items() for s in d['subs']]
    extra_subs = sorted(set((r.group, r.sub) for r in recs) - set(tree_rows))
    for g, s in tree_rows + extra_subs:
        ws.cell(row=row, column=1, value=g).font = body
        ws.cell(row=row, column=2, value=s).font = bold
        ws.cell(row=row, column=3, value=f'=COUNTIFS({G},$A{row},{S},$B{row})')
        ws.cell(row=row, column=4, value=f'=COUNTIFS({G},$A{row},{S},$B{row},{Z},"{CORE_ZONE}")')
        ws.cell(row=row, column=5, value=f'=COUNTIFS({G},$A{row},{S},$B{row},{Z},"{RING_ZONE}")')
        ws.cell(row=row, column=6, value=f'=IF(C{row}=0,"No matches yet",IF(C{row}<5,"Thin",'
                                         f'IF(C{row}<20,"Covered","Well covered")))')
        for c in range(1, 7):
            cell = ws.cell(row=row, column=c); cell.border = box
            if c in (3, 4, 5): cell.alignment = center
            if c == 6: cell.font = body
        row += 1
    widths(ws, [30, 34, 10, 16, 12, 18])
    ws.freeze_panes = 'A5'
    ws.auto_filter.ref = f'A4:F{row - 1}'
    meta['checks']['tree_rows'] = row - 5

    # ============================== RESEARCH MATRIX ==========================
    ws = wb.create_sheet('RESEARCH MATRIX')
    ws.sheet_view.showGridLines = False
    ws['A1'] = 'RESEARCH MATRIX - WHERE THE GAPS ARE'; ws['A1'].font = title_font
    ws['A2'] = ('Targets are planning benchmarks scaled by zone (core catchments carry a higher target than ring '
                'areas). Sort by Gap to see what to canvass next.')
    ws['A2'].font = sub_font
    ws.merge_cells('A1:H1'); ws.merge_cells('A2:H2')
    hdr = ['Catchment', 'Zone', 'Category Group', 'Found', 'Target', 'Gap', 'Coverage', 'Next Action']
    for i, h in enumerate(hdr, start=1): ws.cell(row=4, column=i, value=h)
    style_header(ws, 4, len(hdr))
    row = 5
    for a in AREAS:
        core = a in CORE
        for g in GROUPS:
            ws.cell(row=row, column=1, value=a).font = body
            ws.cell(row=row, column=2, value=CORE_ZONE if core else RING_ZONE).font = body
            ws.cell(row=row, column=3, value=g).font = bold
            ws.cell(row=row, column=4, value=f'=COUNTIFS({A},$A{row},{G},$C{row})')
            ws.cell(row=row, column=5, value=30 if core else 15)
            ws.cell(row=row, column=6, value=f'=MAX(0,E{row}-D{row})')
            ws.cell(row=row, column=7, value=f'=IFERROR(MIN(1,D{row}/E{row}),0)').number_format = '0%'
            ws.cell(row=row, column=8, value=f'=IF(D{row}>=E{row},"Maintain - re-check quarterly",'
                                             f'"Canvass "&$A{row}&" for "&$C{row})')
            for c in range(1, 9):
                cell = ws.cell(row=row, column=c); cell.border = box
                if c in (4, 5, 6, 7): cell.alignment = center
                if c == 8: cell.font = body
            row += 1
    widths(ws, [26, 15, 30, 10, 10, 10, 12, 50])
    ws.freeze_panes = 'A5'
    ws.auto_filter.ref = f'A4:H{row - 1}'

    # ============================== README ===================================
    ws = wb.create_sheet('README', 1)
    write_readme(ws, 'HOW THIS DATABASE IS BUILT', readme_rows(recs, cfg, searches, info, CORE, RING))
    widths(ws, [24, 30, 22, 22, 22, 22])

    # ============================== SOURCE LOG ===============================
    ws = wb.create_sheet('SOURCE LOG')
    write_source_log(ws, recs, searches)

    del wb['Sheet']
    wb._sheets = [wb[n] for n in ['DASHBOARD', 'README', 'MASTER DATABASE', 'AREA SUMMARY',
                                  'GROUP x AREA', 'CATEGORY TREE', 'RESEARCH MATRIX', 'SOURCE LOG']]
    return wb, meta


def readme_rows(recs, cfg, searches, info, CORE, RING):
    by_kind = collections.Counter()
    for r in recs:
        for s in set(r.sources_all or [r.source]):
            by_kind[source_kind(s)] += 1
    done = [s for s in searches if s['status'] == 'done']
    failed = [s for s in searches if s['status'] == 'error']
    n_conf = sum(len(r.conflicts) for r in recs)
    n_out = sum(1 for r in recs if r.area == OUTSIDE)
    n_un = sum(1 for r in recs if r.area == UNASSIGNED)
    not_built = info.get('sources_not_built') or []
    kinds = ', '.join(f'{k}: {v}' for k, v in sorted(by_kind.items())) or 'none'
    rows = [
        ('What this is', f'A sales-ready directory of businesses across {", ".join(CORE) or "(no core areas)"} '
                         f'and {len(RING)} surrounding areas, classified against the full 29-group / '
                         '436-subcategory tree.'),
        ('Catchments', f'Core: {", ".join(CORE) or "none"}. Ring: {", ".join(RING) or "none"}. The Zone column '
                       'lets you filter core-only in one click. Businesses found outside every catchment are kept '
                       f'as "{OUTSIDE}" ({n_out}) - future expansion leads - but are not in the headline counts. '
                       f'"{UNASSIGNED}" ({n_un}) records had no coordinates and no area name in their address.'),
        ('How areas were set', 'Area centres were derived empirically from businesses whose address explicitly '
                               'names the area (median position), not from geocoding the area name. Each record '
                               'is assigned to its nearest centre if it lies within that area\'s radius.'),
        ('Category structure', 'Three levels. Category Group (29) -> Subcategory (436) -> Source Category (the raw '
                               'source label, kept verbatim). The old 18-category value is kept in its own column.'),
        ('How it was collected', f'Run {info["run_id"]}, built {info["today"]}. {len(done)} searches completed'
                                 + (f', {len(failed)} failed (see SOURCE LOG)' if failed else '')
                                 + f'. Records by source type (a record can count under several): {kinds}.'
                                 + (f' Sources configured but not yet built, so not run: {", ".join(not_built)}.'
                                    if not_built else '')),
        ('Deduplication', 'Matched on Google place ID, then normalised phone, then normalised name plus street, '
                          'then normalised name. Where records merged, empty fields were filled from the duplicate '
                          'and the source marked as cross-verified. Where two sources disagreed, the more trusted '
                          f'value was kept (Google > OpenStreetMap > directory > manual); {n_conf} such conflicts '
                          'are recorded in master.json.'),
        ('Prospect priority', 'A = core catchment, has a phone, and either a website or 10+ reviews. B = has a '
                              'phone and is either core catchment or has 25+ reviews. C = has a phone. D = no '
                              'contact number captured yet.'),
        ('Honest limitations', 'Coverage is strongest where businesses maintain Google listings. Small unlisted '
                               'shops - roadside vulcanisers, table-top provision sellers, home-based caterers - '
                               'are under-represented and need street canvassing. Subcategories showing zero on the '
                               'CATEGORY TREE tab are research gaps, not proof of absence.'),
        ('How it was gathered (conduct)', 'Free sources only. Google Maps listing pages were read at low volume, '
                                          'like a person browsing; no CAPTCHA was solved, no login bypassed. '
                                          'Directory and business websites were fetched only where robots.txt '
                                          'allows.'),
        ('Data protection', 'This is a B2B contact list of business details (business names, phones, addresses). '
                            'Nigeria\'s NDPA applies to how it is used: contact businesses as businesses, and '
                            'honour every opt-out by setting Sales Status to "Do Not Contact".'),
        ('How to use it', 'Filter MASTER DATABASE by Zone, Catchment, Category Group and Prospect Priority to build '
                          'a call list. Record outcomes in Sales Status and Sales Notes. Every summary tab '
                          'recalculates from whatever is in MASTER DATABASE.'),
    ]
    if by_kind.get('osm'):
        rows.append(('Attribution', 'Rows sourced from OpenStreetMap: © OpenStreetMap contributors, available '
                                    'under the Open Database Licence (ODbL).'))
    return rows


def write_source_log(ws, recs, searches):
    ws.sheet_view.showGridLines = False
    ws['A1'] = 'WHERE THE DATA CAME FROM'; ws['A1'].font = title_font; ws.merge_cells('A1:H1')
    ws['A2'] = ('Kept = rows from that search that landed inside a configured catchment, before deduplication.')
    ws['A2'].font = sub_font; ws.merge_cells('A2:H2')
    hdr = ['Source', 'Records in database (incl. cross-verified)']
    for i, h in enumerate(hdr, start=1): ws.cell(row=4, column=i, value=h)
    style_header(ws, 4, 2)
    cnt = collections.Counter()
    for r in recs:
        for s in set(r.sources_all or [r.source]):
            cnt[s] += 1
    row = 5
    for s, n in cnt.most_common():
        ws.cell(row=row, column=1, value=s).font = body
        ws.cell(row=row, column=2, value=n).alignment = center
        for c in (1, 2): ws.cell(row=row, column=c).border = box
        row += 1
    row += 1
    hdr = ['Source', 'Search term', 'Area / viewport', 'Status', 'Started (UTC)', 'Finished (UTC)', 'Raw count',
           'Kept count', 'Error']
    for i, h in enumerate(hdr, start=1): ws.cell(row=row, column=i, value=h)
    style_header(ws, row, len(hdr))
    for s in searches:
        row += 1
        vals = [s['source'], s['term'], s['area'], s['status'], s['started_at'], s['finished_at'],
                s['raw_count'], s['kept_count'], s['error']]
        for i, v in enumerate(vals, start=1):
            cell = ws.cell(row=row, column=i, value=blank(v)); cell.font = body; cell.border = box
    widths(ws, [32, 30, 36, 10, 22, 22, 10, 10, 50])
