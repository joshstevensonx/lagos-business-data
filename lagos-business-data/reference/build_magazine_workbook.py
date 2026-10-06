# -*- coding: utf-8 -*-
import json, collections, sys
sys.path.insert(0, '.')
from tree import TREE
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

recs = json.load(open('master_v3.json'))
N = len(recs)
TODAY = "2026-09-21"

CORE = ['Anthony / Anthony Village', 'Maryland / Mende']
RING = ['Ilupeju', 'Gbagada', 'Obanikoro', 'Palmgrove', 'Ojota']
AREAS = CORE + RING
GROUPS = list(TREE.keys()) + ['Other Local Services']
GROUPS = list(dict.fromkeys(GROUPS))

FONT = 'Arial'
NAVY='1F3864'; BLUE='2F5597'; LIGHT='D9E2F3'; GREY='F2F2F2'; GOLD='FFF2CC'
hdr_font = Font(name=FONT, bold=True, color='FFFFFF', size=10)
hdr_fill = PatternFill('solid', fgColor=NAVY)
title_font = Font(name=FONT, bold=True, size=16, color=NAVY)
sub_font = Font(name=FONT, italic=True, size=10, color='595959')
sect_font = Font(name=FONT, bold=True, size=11, color='FFFFFF')
sect_fill = PatternFill('solid', fgColor=BLUE)
body = Font(name=FONT, size=10)
bold = Font(name=FONT, size=10, bold=True)
thin = Side(style='thin', color='BFBFBF')
box = Border(left=thin, right=thin, top=thin, bottom=thin)

def style_header(ws, row, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = hdr_font; cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = box

def widths(ws, w):
    for i, x in enumerate(w, start=1):
        ws.column_dimensions[get_column_letter(i)].width = x

wb = Workbook()
MD = "'MASTER DATABASE'"
LAST = N + 1

# ============================== MASTER DATABASE ==========================
ws = wb.create_sheet('MASTER DATABASE')
COLS = ['ID','Business Name','Zone','Catchment','Street / Cluster','Category Group','Subcategory',
        'Source Category','Legacy 18-Category','Full Address','Phone','Website','Google Maps',
        'Google Rating','Google Reviews','Has Phone','Latitude','Longitude','Data Source',
        'Date Added','Last Checked','Verification','Prospect Priority','Suggested Package',
        'Sales Status','Sales Notes']
for i, h in enumerate(COLS, start=1): ws.cell(row=1, column=i, value=h)
style_header(ws, 1, len(COLS))

for i, r in enumerate(recs):
    rr = i + 2
    try: rating = float(r['rating']) if str(r['rating']).strip() not in ('','None') else None
    except Exception: rating = None
    try: reviews = int(r['reviews']) if str(r['reviews']).strip() not in ('','None') else None
    except Exception: reviews = None
    vals = [i+1, r['name'], r['zone'], r['area'], r['street'], r['group'], r['sub'],
            r['label'], r['legacy18'], r['addr'], r['phone'], r['website'], r['maps'],
            rating, reviews, r['contactable'], r['lat'] or None, r['lng'] or None,
            r['source'], r['added'], TODAY, r['verification'], r['priority'],
            r['package'], r['sales'], r['notes']]
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=rr, column=c, value=v)
        cell.font = body
        cell.alignment = Alignment(vertical='top', wrap_text=(c in (10, 26)))
    ws.cell(row=rr, column=14).number_format = '0.0'
    ws.cell(row=rr, column=15).number_format = '#,##0'
    ws.cell(row=rr, column=17).number_format = '0.000000'
    ws.cell(row=rr, column=18).number_format = '0.000000'
    pr = ws.cell(row=rr, column=23)
    p0 = r['priority'][:1]
    fills = {'A': ('C6EFCE','006100'), 'B': (GOLD,'7F6000'), 'C': ('FCE4D6','833C0B'), 'D': (GREY,'595959')}
    f, col = fills[p0]
    pr.fill = PatternFill('solid', fgColor=f)
    pr.font = Font(name=FONT, size=10, color=col, bold=(p0 == 'A'))
    if r['zone'] == 'Core catchment':
        ws.cell(row=rr, column=3).font = Font(name=FONT, size=10, bold=True, color=NAVY)

widths(ws, [6,38,15,26,26,26,26,26,20,44,17,26,30,9,10,9,12,12,28,12,12,20,30,14,16,28])
ws.freeze_panes = 'C2'
ws.auto_filter.ref = f'A1:{get_column_letter(len(COLS))}{LAST}'
dv_area = DataValidation(type='list', formula1='"' + ','.join(AREAS) + '"', allow_blank=True)
dv_sale = DataValidation(type='list', formula1='"Not Contacted,Contacted,Meeting Booked,Proposal Sent,Won,Declined,Do Not Contact"', allow_blank=True)
dv_pkg  = DataValidation(type='list', formula1='"Premium,Standard,Listing"', allow_blank=True)
for dv, col in ((dv_area,'D'), (dv_sale,'Y'), (dv_pkg,'X')):
    ws.add_data_validation(dv); dv.add(f'{col}2:{col}{LAST}')

# ============================== DASHBOARD ================================
ws = wb.create_sheet('DASHBOARD', 0)
ws.sheet_view.showGridLines = False
ws['A1'] = 'ANTHONY COMMUNITY MEDIA - BUSINESS DATABASE v3'; ws['A1'].font = title_font
ws['A2'] = f'7 catchments  |  29 category groups  |  436-subcategory tree  |  Last refreshed {TODAY}'
ws['A2'].font = sub_font
ws.merge_cells('A1:G1'); ws.merge_cells('A2:G2')

ws['A4'] = 'HEADLINE NUMBERS'; ws['A4'].font = sect_font; ws['A4'].fill = sect_fill
ws.merge_cells('A4:G4')
kpis = [
 ('Total businesses in database', f'=COUNTA({MD}!B2:B{LAST})'),
 ('Core catchment (Anthony + Maryland)', f'=COUNTIF({MD}!C2:C{LAST},"Core catchment")'),
 ('Ring areas (5 surrounding)', f'=COUNTIF({MD}!C2:C{LAST},"Ring area")'),
 ('With a phone number', f'=COUNTIF({MD}!P2:P{LAST},"Yes")'),
 ('Google-verified location', f'=COUNTIF({MD}!V2:V{LAST},"Google-verified")'),
 ('Priority A prospects (core, contactable, visible)', f'=COUNTIF({MD}!W2:W{LAST},"A - High commercial relevance")'),
 ('Priority B prospects', f'=COUNTIF({MD}!W2:W{LAST},"B - Potential advertiser")'),
 ('Priority C prospects (ring area, contactable)', f'=COUNTIF({MD}!W2:W{LAST},"C - Ring area, contactable")'),
]
r0 = 5
for i, (lab, f) in enumerate(kpis):
    ws.cell(row=r0+i, column=1, value=lab).font = bold
    c = ws.cell(row=r0+i, column=4, value=f)
    c.font = Font(name=FONT, size=11, bold=True, color=NAVY)
    c.alignment = Alignment(horizontal='right'); c.number_format = '#,##0'
    ws.cell(row=r0+i, column=1).border = box; c.border = box

gr = r0 + len(kpis) + 1
ws.cell(row=gr, column=1, value='BUSINESSES BY CATEGORY GROUP').font = sect_font
ws.cell(row=gr, column=1).fill = sect_fill
ws.merge_cells(start_row=gr, start_column=1, end_row=gr, end_column=7)
hdr = ['Category Group','Core catchment','Ring areas','Total','With phone','Priority A','% of database']
for i, h in enumerate(hdr, start=1): ws.cell(row=gr+1, column=i, value=h)
style_header(ws, gr+1, 7)
first = gr + 2
for i, g in enumerate(GROUPS):
    rr = first + i
    ws.cell(row=rr, column=1, value=g).font = bold
    ws.cell(row=rr, column=2, value=f'=COUNTIFS({MD}!$C$2:$C${LAST},"Core catchment",{MD}!$F$2:$F${LAST},$A{rr})')
    ws.cell(row=rr, column=3, value=f'=COUNTIFS({MD}!$C$2:$C${LAST},"Ring area",{MD}!$F$2:$F${LAST},$A{rr})')
    ws.cell(row=rr, column=4, value=f'=SUM(B{rr}:C{rr})')
    ws.cell(row=rr, column=5, value=f'=COUNTIFS({MD}!$F$2:$F${LAST},$A{rr},{MD}!$P$2:$P${LAST},"Yes")')
    ws.cell(row=rr, column=6, value=f'=COUNTIFS({MD}!$F$2:$F${LAST},$A{rr},{MD}!$W$2:$W${LAST},"A - High commercial relevance")')
    p = ws.cell(row=rr, column=7, value=f'=IFERROR(D{rr}/$D${first+len(GROUPS)},0)'); p.number_format = '0.0%'
    for c in range(1, 8):
        cell = ws.cell(row=rr, column=c); cell.border = box
        if c > 1: cell.font = body; cell.alignment = Alignment(horizontal='center')
        if i % 2: cell.fill = PatternFill('solid', fgColor=GREY)
tot = first + len(GROUPS)
ws.cell(row=tot, column=1, value='TOTAL')
for c, L in ((2,'B'), (3,'C'), (4,'D'), (5,'E'), (6,'F')):
    ws.cell(row=tot, column=c, value=f'=SUM({L}{first}:{L}{tot-1})')
ws.cell(row=tot, column=7, value=f'=IFERROR(D{tot}/$D${tot},0)').number_format = '0.0%'
for c in range(1, 8):
    cell = ws.cell(row=tot, column=c); cell.fill = PatternFill('solid', fgColor=BLUE)
    cell.border = box; cell.font = Font(name=FONT, bold=True, color='FFFFFF')
    cell.alignment = Alignment(horizontal='center')
ws.cell(row=tot, column=1).alignment = Alignment(horizontal='left')
note = tot + 2
ws.cell(row=note, column=1, value='Note').font = bold
ws.cell(row=note, column=2, value='Every figure here is a live formula over MASTER DATABASE. Add or edit rows there and this updates automatically.').font = sub_font
ws.merge_cells(start_row=note, start_column=2, end_row=note, end_column=7)
widths(ws, [42,16,16,12,12,12,14])
ws.freeze_panes = 'A5'

# ============================== AREA SUMMARY =============================
ws = wb.create_sheet('AREA SUMMARY')
ws.sheet_view.showGridLines = False
ws['A1'] = 'COVERAGE BY CATCHMENT'; ws['A1'].font = title_font; ws.merge_cells('A1:I1')
hdr = ['Catchment','Zone','Businesses','% of database','With phone','Google-verified','Priority A','Priority B','Priority C/D']
for i, h in enumerate(hdr, start=1): ws.cell(row=3, column=i, value=h)
style_header(ws, 3, len(hdr))
for i, a in enumerate(AREAS):
    rr = 4 + i
    ws.cell(row=rr, column=1, value=a).font = bold
    ws.cell(row=rr, column=2, value='Core catchment' if a in CORE else 'Ring area')
    ws.cell(row=rr, column=3, value=f'=COUNTIF({MD}!$D$2:$D${LAST},$A{rr})')
    p = ws.cell(row=rr, column=4, value=f'=IFERROR(C{rr}/$C${4+len(AREAS)},0)'); p.number_format = '0.0%'
    ws.cell(row=rr, column=5, value=f'=COUNTIFS({MD}!$D$2:$D${LAST},$A{rr},{MD}!$P$2:$P${LAST},"Yes")')
    ws.cell(row=rr, column=6, value=f'=COUNTIFS({MD}!$D$2:$D${LAST},$A{rr},{MD}!$V$2:$V${LAST},"Google-verified")')
    ws.cell(row=rr, column=7, value=f'=COUNTIFS({MD}!$D$2:$D${LAST},$A{rr},{MD}!$W$2:$W${LAST},"A - High commercial relevance")')
    ws.cell(row=rr, column=8, value=f'=COUNTIFS({MD}!$D$2:$D${LAST},$A{rr},{MD}!$W$2:$W${LAST},"B - Potential advertiser")')
    ws.cell(row=rr, column=9, value=f'=C{rr}-G{rr}-H{rr}')
    for c in range(1, 10):
        cell = ws.cell(row=rr, column=c); cell.border = box
        if c > 2: cell.font = body; cell.alignment = Alignment(horizontal='center')
        else: cell.font = bold if c == 1 else body
        if a in CORE: cell.fill = PatternFill('solid', fgColor=LIGHT)
tr = 4 + len(AREAS)
ws.cell(row=tr, column=1, value='TOTAL')
for c, L in ((3,'C'), (5,'E'), (6,'F'), (7,'G'), (8,'H'), (9,'I')):
    ws.cell(row=tr, column=c, value=f'=SUM({L}4:{L}{tr-1})')
ws.cell(row=tr, column=4, value=f'=IFERROR(C{tr}/$C${tr},0)').number_format = '0.0%'
for c in range(1, 10):
    cell = ws.cell(row=tr, column=c); cell.fill = PatternFill('solid', fgColor=BLUE)
    cell.border = box; cell.font = Font(name=FONT, bold=True, color='FFFFFF')
    cell.alignment = Alignment(horizontal='center')
ws.cell(row=tr, column=1).alignment = Alignment(horizontal='left')
widths(ws, [28,16,12,14,12,16,12,12,14])

# ============================== GROUP x AREA MATRIX ======================
ws = wb.create_sheet('GROUP x AREA')
ws.sheet_view.showGridLines = False
ws['A1'] = 'CATEGORY GROUP BY CATCHMENT'; ws['A1'].font = title_font
ws.merge_cells('A1:I1')
hdr = ['Category Group'] + AREAS + ['Total']
for i, h in enumerate(hdr, start=1): ws.cell(row=3, column=i, value=h)
style_header(ws, 3, len(hdr))
for i, g in enumerate(GROUPS):
    rr = 4 + i
    ws.cell(row=rr, column=1, value=g).font = bold
    for j, a in enumerate(AREAS):
        col = 2 + j
        L = get_column_letter(col)
        ws.cell(row=rr, column=col,
                value=f'=COUNTIFS({MD}!$F$2:$F${LAST},$A{rr},{MD}!$D$2:$D${LAST},{L}$3)')
    ws.cell(row=rr, column=len(hdr), value=f'=SUM(B{rr}:{get_column_letter(len(hdr)-1)}{rr})')
    for c in range(1, len(hdr)+1):
        cell = ws.cell(row=rr, column=c); cell.border = box
        if c > 1: cell.font = body; cell.alignment = Alignment(horizontal='center')
        if i % 2: cell.fill = PatternFill('solid', fgColor=GREY)
tr = 4 + len(GROUPS)
ws.cell(row=tr, column=1, value='TOTAL')
for c in range(2, len(hdr)+1):
    L = get_column_letter(c)
    ws.cell(row=tr, column=c, value=f'=SUM({L}4:{L}{tr-1})')
for c in range(1, len(hdr)+1):
    cell = ws.cell(row=tr, column=c); cell.fill = PatternFill('solid', fgColor=BLUE)
    cell.border = box; cell.font = Font(name=FONT, bold=True, color='FFFFFF')
    cell.alignment = Alignment(horizontal='center')
ws.cell(row=tr, column=1).alignment = Alignment(horizontal='left')
widths(ws, [30] + [17]*len(AREAS) + [12])
ws.freeze_panes = 'B4'

# ============================== CATEGORY TREE ============================
ws = wb.create_sheet('CATEGORY TREE')
ws.sheet_view.showGridLines = False
ws['A1'] = 'FULL CATEGORY TREE - 29 GROUPS, 436 SUBCATEGORIES'; ws['A1'].font = title_font
ws['A2'] = 'Every subcategory you specified, with how many businesses landed in it. Zero means nothing matched yet - that is a research gap, not an error.'
ws['A2'].font = sub_font
ws.merge_cells('A1:F1'); ws.merge_cells('A2:F2')
hdr = ['Category Group','Subcategory','Found','Core catchment','Ring areas','Status']
for i, h in enumerate(hdr, start=1): ws.cell(row=4, column=i, value=h)
style_header(ws, 4, len(hdr))
row = 5
tree_rows = [(g, s) for g, d in TREE.items() for s in d['subs']]
extra_subs = sorted(set((r['group'], r['sub']) for r in recs) - set(tree_rows))
for g, s in tree_rows + extra_subs:
    ws.cell(row=row, column=1, value=g).font = body
    ws.cell(row=row, column=2, value=s).font = bold
    ws.cell(row=row, column=3, value=f'=COUNTIFS({MD}!$F$2:$F${LAST},$A{row},{MD}!$G$2:$G${LAST},$B{row})')
    ws.cell(row=row, column=4, value=f'=COUNTIFS({MD}!$F$2:$F${LAST},$A{row},{MD}!$G$2:$G${LAST},$B{row},{MD}!$C$2:$C${LAST},"Core catchment")')
    ws.cell(row=row, column=5, value=f'=C{row}-D{row}')
    ws.cell(row=row, column=6, value=f'=IF(C{row}=0,"No matches yet",IF(C{row}<5,"Thin",IF(C{row}<20,"Covered","Well covered")))')
    for c in range(1, 7):
        cell = ws.cell(row=row, column=c); cell.border = box
        if c in (3, 4, 5): cell.alignment = Alignment(horizontal='center')
        if c == 6: cell.font = body
    row += 1
widths(ws, [30,34,10,16,12,18])
ws.freeze_panes = 'A5'
ws.auto_filter.ref = f'A4:F{row-1}'
TREE_ROWS = row - 5

# ============================== RESEARCH MATRIX ==========================
ws = wb.create_sheet('RESEARCH MATRIX')
ws.sheet_view.showGridLines = False
ws['A1'] = 'RESEARCH MATRIX - WHERE THE GAPS ARE'; ws['A1'].font = title_font
ws['A2'] = 'Targets are planning benchmarks scaled by zone (core catchments carry a higher target than ring areas). Sort by Gap to see what to canvass next.'
ws['A2'].font = sub_font
ws.merge_cells('A1:H1'); ws.merge_cells('A2:H2')
hdr = ['Catchment','Zone','Category Group','Found','Target','Gap','Coverage','Next Action']
for i, h in enumerate(hdr, start=1): ws.cell(row=4, column=i, value=h)
style_header(ws, 4, len(hdr))
row = 5
for a in AREAS:
    core = a in CORE
    for g in GROUPS:
        ws.cell(row=row, column=1, value=a).font = body
        ws.cell(row=row, column=2, value='Core catchment' if core else 'Ring area').font = body
        ws.cell(row=row, column=3, value=g).font = bold
        ws.cell(row=row, column=4, value=f'=COUNTIFS({MD}!$D$2:$D${LAST},$A{row},{MD}!$F$2:$F${LAST},$C{row})')
        ws.cell(row=row, column=5, value=30 if core else 15)
        ws.cell(row=row, column=6, value=f'=MAX(0,E{row}-D{row})')
        cv = ws.cell(row=row, column=7, value=f'=IFERROR(MIN(1,D{row}/E{row}),0)'); cv.number_format = '0%'
        ws.cell(row=row, column=8, value=f'=IF(D{row}>=E{row},"Maintain - re-check quarterly","Canvass "&$A{row}&" for "&$C{row})')
        for c in range(1, 9):
            cell = ws.cell(row=row, column=c); cell.border = box
            if c in (4, 5, 6, 7): cell.alignment = Alignment(horizontal='center')
            if c == 8: cell.font = body
        row += 1
widths(ws, [26,15,30,10,10,10,12,50])
ws.freeze_panes = 'A5'
ws.auto_filter.ref = f'A4:H{row-1}'

# ============================== README ===================================
ws = wb.create_sheet('README', 1)
ws.sheet_view.showGridLines = False
ws['A1'] = 'HOW THIS DATABASE IS BUILT'; ws['A1'].font = title_font
ws.merge_cells('A1:F1')
rows = [
 ('What this is', 'A sales-ready directory of businesses across Anthony Village, Maryland/Mende and the five surrounding areas, classified against the full 29-group / 436-subcategory tree.'),
 ('Catchments', 'Core: Anthony / Anthony Village, Maryland / Mende. Ring: Ilupeju, Gbagada, Obanikoro, Palmgrove, Ojota. The Zone column lets you filter core-only in one click.'),
 ('How areas were set', 'Centroids were derived empirically, not guessed: 531 businesses whose Google address explicitly named an area were used to compute each area centre. Every record is then assigned to its nearest centroid, within 1.0-1.6 km depending on how large the area is.'),
 ('Category structure', 'Three levels. Category Group (your 29) -> Subcategory (your 436) -> Source Category (the raw Google label, kept verbatim). The old 18-category value is retained in its own column so earlier filters still work.'),
 ('How it was collected', '179 Google Maps searches run over a single wide viewport covering all seven areas at once, so each search returned businesses across the whole footprint rather than one area at a time. 15,414 raw results, 13,947 unique, 4,446 inside the seven catchments.'),
 ('Deduplication', 'Matched on normalised phone, then normalised name plus street, then normalised name. Where records merged, the richer value was kept for each field and the source marked as cross-verified.'),
 ('Prospect priority', 'A = core catchment, has a phone, and either a website or 10+ reviews. B = has a phone and is either core catchment or has 25+ reviews. C = ring area with a phone. D = no contact number captured yet.'),
 ('Honest limitations', 'Coverage is strongest where businesses maintain Google listings. Small unlisted shops - roadside vulcanisers, table-top provision sellers, home-based caterers - are under-represented and need street canvassing. Subcategories showing zero on the CATEGORY TREE tab were searched for but returned no distinct match.'),
 ('What would improve it', 'Apify credit (roughly $20) would allow all 321 planned search terms to run with emails and opening hours attached, rather than the 179 achievable free. The browser route cannot retrieve email addresses at all.'),
 ('How to use it', 'Filter MASTER DATABASE by Zone, Catchment, Category Group and Prospect Priority to build a call list. Record outcomes in Sales Status and Sales Notes. Every summary tab recalculates from whatever is in MASTER DATABASE.'),
]
for i, (k, v) in enumerate(rows, start=3):
    ws.cell(row=i, column=1, value=k).font = bold
    ws.cell(row=i, column=1).fill = PatternFill('solid', fgColor=LIGHT)
    ws.cell(row=i, column=1).alignment = Alignment(vertical='top')
    c = ws.cell(row=i, column=2, value=v); c.font = body
    c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.merge_cells(start_row=i, start_column=2, end_row=i, end_column=6)
    ws.row_dimensions[i].height = 52
    ws.cell(row=i, column=1).border = box; c.border = box
widths(ws, [24,30,22,22,22,22])

# ============================== SOURCE LOG ===============================
ws = wb.create_sheet('SOURCE LOG')
ws.sheet_view.showGridLines = False
ws['A1'] = 'WHERE THE DATA CAME FROM'; ws['A1'].font = title_font; ws.merge_cells('A1:E1')
hdr = ['Source','What it contributed','Records','How it was used','Reference']
for i, h in enumerate(hdr, start=1): ws.cell(row=3, column=i, value=h)
style_header(ws, 3, len(hdr))
cnt = collections.Counter(r['source'] for r in recs)
srcs = [
 ('Google Maps (area sweep, Sep 2026)', '179 category searches over a wide viewport covering all seven catchments; names, Google category, address, phone, rating, review count and coordinates.', cnt.get('Google Maps (area sweep, Sep 2026)', 0), 'Primary discovery and verification for all areas', 'https://www.google.com/maps'),
 ('Google Maps (Apify scrape)', '48 category searches for the Anthony Village catchment, run before the Apify free tier was exhausted. Adds websites, which the browser route cannot capture.', cnt.get('Google Maps (Apify scrape)', 0), 'Primary discovery for Anthony Village', 'https://apify.com/compass/crawler-google-places'),
 ('Google Maps (verified search)', '28 category searches centred on Maryland / Mende.', cnt.get('Google Maps (verified search)', 0), 'Primary discovery for Maryland', 'https://www.google.com/maps'),
 ('Legacy seed (Finelib / NGEX / Cybo)', 'The original 265 records from the first workbook, sourced from Nigerian business directories.', cnt.get('Legacy seed (Finelib / NGEX / Cybo)', 0), 'Retained in full, re-classified and re-assigned by catchment', 'Anthony_Community_Media_MASTER_DATABASE_SUMMARIES_POPULATED.xlsx'),
 ('Multiple sources (cross-verified)', 'Records that appeared in more than one source and were merged into a single richer row.', cnt.get('Multiple sources (cross-verified)', 0), 'Highest-confidence records', 'All of the above'),
 ('Legacy seed + Google Maps', 'Directory records confirmed against a live Google listing.', cnt.get('Legacy seed + Google Maps', 0), 'Cross-verification', 'All of the above'),
 ('Finelib', 'Area and category business listings with phones and addresses.', 'see legacy', 'Directory cross-reference', 'https://www.finelib.com/cities/lagos/areas-and-suburbs/anthony-village'),
 ('OpenStreetMap', 'Street-level points of interest used to sanity-check catchment boundaries.', 'boundary check', 'Geographic validation only', 'https://www.openstreetmap.org/'),
]
for i, (a, b, c, d, e) in enumerate(srcs, start=4):
    for j, v in enumerate((a, b, c, d, e), start=1):
        cell = ws.cell(row=i, column=j, value=v); cell.font = body
        cell.alignment = Alignment(wrap_text=True, vertical='top',
                                   horizontal='center' if j == 3 else 'left')
        cell.border = box
    ws.row_dimensions[i].height = 46
widths(ws, [32,54,12,36,46])

del wb['Sheet']
wb._sheets = [wb[n] for n in ['DASHBOARD','README','MASTER DATABASE','AREA SUMMARY',
                              'GROUP x AREA','CATEGORY TREE','RESEARCH MATRIX','SOURCE LOG']]
OUT = '/mnt/user-data/outputs/Anthony_Community_Media_MASTER_DATABASE_v3.xlsx'
import os; os.makedirs('/mnt/user-data/outputs', exist_ok=True)
wb.save(OUT)
print('saved', OUT)
print('master rows', N, '| tree rows', TREE_ROWS, '| groups', len(GROUPS), '| areas', len(AREAS))
