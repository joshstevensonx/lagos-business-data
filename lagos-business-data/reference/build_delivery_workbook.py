# -*- coding: utf-8 -*-
"""Build the Lagos delivery-prospects workbook from scored records.

Input : /home/claude/delivery/prospects.json  (list of dicts, see score.py)
Output: /mnt/user-data/outputs/Lagos_Delivery_Prospects.xlsx
"""
import json, collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score import COMPONENTS, band
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HERE = os.path.dirname(os.path.abspath(__file__))
recs = json.load(open(os.path.join(HERE, 'prospects.json')))
TODAY = '2026-10-06'
AREAS = ['Lekki Phase 1', 'Lekki / Ajah corridor', 'Victoria Island', 'Ikoyi', 'Yaba', 'Surulere']
CATS = ['Restaurant / Food', 'Supermarket / Grocery', 'Pharmacy', 'Other']
BANDS = ['Hot - approach first', 'Warm - worth a call',
         'Cool - lower priority', 'Cold - little evidence of delivery']

FONT = 'Arial'
NAVY = '1F3864'; BLUE = '2F5597'; LIGHT = 'D9E2F3'; GREY = 'F2F2F2'
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

def style_header(ws, row, n):
    for c in range(1, n + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = hdr_font; cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = box

def widths(ws, w):
    for i, x in enumerate(w, start=1):
        ws.column_dimensions[get_column_letter(i)].width = x

recs.sort(key=lambda r: (-r['score'], r['area'], r['name'].lower()))
N = len(recs)
LAST = N + 1
wb = Workbook()
TL = "'TARGET LIST'"

# ---------------------------------------------------------------- TARGET LIST
ws = wb.create_sheet('TARGET LIST')
COLS = (['Rank', 'Business Name', 'Area', 'Category', 'Google Category',
         'Delivery Score', 'Band', 'Delivery flag (Google)', 'Catering', 'Chain',
         'Score basis', 'Google Rating', 'Reviews', 'Phone', 'All Phones', 'Website', 'Email',
         'Instagram', 'Facebook', 'LinkedIn', 'Contact Channels', 'Full Address',
         'Latitude', 'Longitude', 'Google Maps', 'Data Source', 'Last Checked',
         'Approach Status', 'Notes'])
for i, h in enumerate(COLS, start=1):
    ws.cell(row=1, column=i, value=h)
style_header(ws, 1, len(COLS))

for i, r in enumerate(recs):
    rr = i + 2
    ch = r['contacts']
    vals = [i + 1, r['name'], r['area'], r['category'], r['google_category'],
            r['score'], r['band'],
            'Yes' if r['components'].get('Google Delivery flag') else 'No',
            'Yes' if r['components'].get('Catering offered') else 'No',
            'Yes' if r['components'].get('Chain / multi-branch') else 'No',
            'Full - delivery data checked' if 'full detail' in r.get('source','')
                else 'Basic - delivery not yet checked',
            r.get('rating') or None, r.get('reviews') or None,
            ch.get('phone', ''), ch.get('phones_all', ''), ch.get('website', ''),
            ch.get('email', ''), ch.get('instagram', ''), ch.get('facebook', ''),
            ch.get('linkedin', ''), ch.get('count', 0), r.get('address', ''),
            r.get('lat') or None, r.get('lng') or None, r.get('maps', ''),
            r.get('source', ''), TODAY, 'Not approached', '']
    for c, v in enumerate(vals, start=1):
        cell = ws.cell(row=rr, column=c, value=v)
        cell.font = body
        cell.alignment = Alignment(vertical='top', wrap_text=(c in (21, 28)))
    ws.cell(row=rr, column=12).number_format = '0.0'
    ws.cell(row=rr, column=13).number_format = '#,##0'
    ws.cell(row=rr, column=23).number_format = '0.000000'
    ws.cell(row=rr, column=24).number_format = '0.000000'
    sc = ws.cell(row=rr, column=6); sc.number_format = '0'
    b = r['band']
    fills = {BANDS[0]: ('C6EFCE', '006100'), BANDS[1]: ('FFF2CC', '7F6000'),
             BANDS[2]: ('FCE4D6', '833C0B'), BANDS[3]: (GREY, '595959')}
    f, col = fills[b]
    for c in (6, 7):
        cell = ws.cell(row=rr, column=c)
        cell.fill = PatternFill('solid', fgColor=f)
        cell.font = Font(name=FONT, size=10, color=col, bold=(b == BANDS[0]))

widths(ws, [6, 38, 22, 22, 24, 13, 28, 16, 10, 9, 28, 10, 9, 17, 26, 32, 30, 32, 32, 32, 11, 44, 12, 12, 30, 26, 12, 18, 30])
ws.freeze_panes = 'C2'
ws.auto_filter.ref = f'A1:{get_column_letter(len(COLS))}{LAST}'
dv = DataValidation(type='list', allow_blank=True,
                    formula1='"Not approached,Contacted,Meeting Booked,Proposal Sent,Trial,Won,Declined"')
ws.add_data_validation(dv); dv.add(f'AB2:AB{LAST}')

# ----------------------------------------------------------------- DASHBOARD
ws = wb.create_sheet('DASHBOARD', 0)
ws.sheet_view.showGridLines = False
ws['A1'] = 'LAGOS DELIVERY PROSPECTS'; ws['A1'].font = title_font
ws['A2'] = ('Restaurants, supermarkets and pharmacies across 5 Lagos areas, ranked by how '
            f'likely they are to need a dedicated delivery partner  |  Built {TODAY}')
ws['A2'].font = sub_font
ws.merge_cells('A1:F1'); ws.merge_cells('A2:F2')

ws['A4'] = 'HEADLINE NUMBERS'; ws['A4'].font = sect_font; ws['A4'].fill = sect_fill
ws.merge_cells('A4:F4')
kpis = [
    ('Total prospects', f'=COUNTA({TL}!B2:B{LAST})'),
    ('Hot - approach first', f'=COUNTIF({TL}!G2:G{LAST},"{BANDS[0]}")'),
    ('Warm - worth a call', f'=COUNTIF({TL}!G2:G{LAST},"{BANDS[1]}")'),
    ('Flagged by Google as doing delivery', f'=COUNTIF({TL}!H2:H{LAST},"Yes")'),
    ('Offer catering (bulk-order signal)', f'=COUNTIF({TL}!I2:I{LAST},"Yes")'),
    ('Chains / multi-branch', f'=COUNTIF({TL}!J2:J{LAST},"Yes")'),
    ('With a phone number', f'=COUNTIF({TL}!N2:N{LAST},"<>")'),
    ('With a website', f'=COUNTIF({TL}!P2:P{LAST},"<>")'),
    ('With an email', f'=COUNTIF({TL}!Q2:Q{LAST},"<>")'),
    ('With Instagram', f'=COUNTIF({TL}!R2:R{LAST},"<>")'),
    ('Delivery data actually checked', f'=COUNTIF({TL}!K2:K{LAST},"Full - delivery data checked")'),
]
r0 = 5
for i, (lab, f) in enumerate(kpis):
    ws.cell(row=r0 + i, column=1, value=lab).font = bold
    c = ws.cell(row=r0 + i, column=3, value=f)
    c.font = Font(name=FONT, size=11, bold=True, color=NAVY)
    c.alignment = Alignment(horizontal='right'); c.number_format = '#,##0'
    ws.cell(row=r0 + i, column=1).border = box; c.border = box

ar = r0 + len(kpis) + 1
ws.cell(row=ar, column=1, value='BY AREA AND CATEGORY').font = sect_font
ws.cell(row=ar, column=1).fill = sect_fill
ws.merge_cells(start_row=ar, start_column=1, end_row=ar, end_column=6)
hdr = ['Area'] + CATS[:3] + ['Total', 'Hot']
for i, h in enumerate(hdr, start=1): ws.cell(row=ar + 1, column=i, value=h)
style_header(ws, ar + 1, len(hdr))
first = ar + 2
for i, a in enumerate(AREAS):
    rr = first + i
    ws.cell(row=rr, column=1, value=a).font = bold
    for j, cat in enumerate(CATS[:3]):
        ws.cell(row=rr, column=2 + j,
                value=f'=COUNTIFS({TL}!$C$2:$C${LAST},$A{rr},{TL}!$D$2:$D${LAST},"{cat}")')
    ws.cell(row=rr, column=5, value=f'=SUM(B{rr}:D{rr})')
    ws.cell(row=rr, column=6,
            value=f'=COUNTIFS({TL}!$C$2:$C${LAST},$A{rr},{TL}!$G$2:$G${LAST},"{BANDS[0]}")')
    for c in range(1, 7):
        cell = ws.cell(row=rr, column=c); cell.border = box
        if c > 1: cell.font = body; cell.alignment = Alignment(horizontal='center')
        if i % 2: cell.fill = PatternFill('solid', fgColor=GREY)
tot = first + len(AREAS)
ws.cell(row=tot, column=1, value='TOTAL')
for c in range(2, 7):
    L = get_column_letter(c)
    ws.cell(row=tot, column=c, value=f'=SUM({L}{first}:{L}{tot - 1})')
for c in range(1, 7):
    cell = ws.cell(row=tot, column=c); cell.fill = PatternFill('solid', fgColor=BLUE)
    cell.border = box; cell.font = Font(name=FONT, bold=True, color='FFFFFF')
    cell.alignment = Alignment(horizontal='center')
ws.cell(row=tot, column=1).alignment = Alignment(horizontal='left')
widths(ws, [38, 20, 22, 14, 12, 10])
ws.freeze_panes = 'A5'

# ------------------------------------------------------------ SCORING METHOD
ws = wb.create_sheet('SCORING METHOD')
ws.sheet_view.showGridLines = False
ws['A1'] = 'HOW THE DELIVERY SCORE IS BUILT'; ws['A1'].font = title_font
ws['A2'] = ('Google has no "does large deliveries" field. This score combines the signals that do '
            'exist, so the ranking is a judgement aid, not a measurement. Every component is shown '
            'so you can disagree with it.')
ws['A2'].font = sub_font
ws.merge_cells('A1:D1'); ws.merge_cells('A2:D2'); ws.row_dimensions[2].height = 30
ws['A2'].alignment = Alignment(wrap_text=True, vertical='top')
hdr = ['Signal', 'Max points', 'Why it matters', 'How many prospects have it']
for i, h in enumerate(hdr, start=1): ws.cell(row=4, column=i, value=h)
style_header(ws, 4, 4)
why = {
    'Google Delivery flag': 'The business itself has told Google it delivers. The single strongest direct signal.',
    'No-contact delivery': 'Indicates an established delivery process rather than ad-hoc drop-offs.',
    'Takeout': 'Food already leaves the premises; delivery is a short step from there.',
    'Delivery hours published': 'Separate delivery opening hours imply a real, staffed delivery operation.',
    'Catering offered': 'The best available proxy for genuinely large orders - the volume worth outsourcing.',
    'Order-volume proxy (reviews)': 'Review count stands in for customer throughput. Logarithmic, so a huge chain cannot dominate.',
    'Has website': 'Suggests a business large enough to have invested in its own channel.',
    'Online ordering / menu': 'An order pipeline already exists, which is what a delivery partner plugs into.',
    'Chain / multi-branch': 'Multiple outlets mean multi-drop routes and a single decision-maker for several sites.',
    'Category weight': 'Supermarkets carry the heaviest baskets, restaurants the most frequent drops, pharmacies the most urgent.',
    'Rating 4.0+': 'A well-run business is a better partner and more likely to protect its delivery experience.',
}
counts = collections.Counter()
for r in recs:
    for k, v in r['components'].items():
        if v: counts[k] += 1
maxpts = {'Google Delivery flag': 25, 'No-contact delivery': 5, 'Takeout': 5,
          'Delivery hours published': 5, 'Catering offered': 15,
          'Order-volume proxy (reviews)': 25, 'Has website': 8,
          'Online ordering / menu': 7, 'Chain / multi-branch': 10,
          'Category weight': 10, 'Rating 4.0+': 5}
for i, comp in enumerate(COMPONENTS, start=5):
    ws.cell(row=i, column=1, value=comp).font = bold
    ws.cell(row=i, column=2, value=maxpts.get(comp, 0)).alignment = Alignment(horizontal='center')
    c = ws.cell(row=i, column=3, value=why.get(comp, '')); c.font = body
    c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.cell(row=i, column=4, value=counts.get(comp, 0)).alignment = Alignment(horizontal='center')
    for cc in range(1, 5):
        ws.cell(row=i, column=cc).border = box
    ws.row_dimensions[i].height = 34
br = 5 + len(COMPONENTS) + 1
ws.cell(row=br, column=1, value='BANDS').font = sect_font
ws.cell(row=br, column=1).fill = sect_fill
ws.merge_cells(start_row=br, start_column=1, end_row=br, end_column=4)
for i, (b, rng) in enumerate(zip(BANDS, ['60 and above', '40 - 59', '25 - 39', 'under 25']), start=br + 1):
    ws.cell(row=i, column=1, value=b).font = bold
    ws.cell(row=i, column=2, value=rng).alignment = Alignment(horizontal='center')
    ws.cell(row=i, column=4, value=sum(1 for r in recs if r['band'] == b)).alignment = Alignment(horizontal='center')
    for cc in range(1, 5): ws.cell(row=i, column=cc).border = box
widths(ws, [32, 14, 72, 24])

# ------------------------------------------------------------------- README
ws = wb.create_sheet('README')
ws.sheet_view.showGridLines = False
ws['A1'] = 'ABOUT THIS LIST'; ws['A1'].font = title_font
ws.merge_cells('A1:E1')
sources = sorted(set(r.get('source', '') for r in recs if r.get('source')))
rows = [
    ('Purpose', 'A prospecting list for approaching restaurants, supermarkets and pharmacies that '
                'move enough volume to need a dedicated delivery partner.'),
    ('Areas covered', ', '.join(AREAS) + '.'),
    ('Categories', 'Restaurants and food outlets, supermarkets and grocery stores, and pharmacies, '
                   'captured through 8 search terms per area so the long tail is included.'),
    ('How to use it', 'The TARGET LIST is sorted by Delivery Score, highest first. Start at the top of '
                      'the Hot band, work down, and record outcomes in Approach Status. Filter by Area '
                      'to plan a day of visits in one part of Lagos.'),
    ('Scoring', 'See the SCORING METHOD tab. Every component that fed each score is shown as its own '
                'column on the TARGET LIST, so you can re-sort on whatever you trust most.'),
    ('Contact details', 'Phone comes from the Google listing. Website, email and social handles come '
                        'from crawling each business website where one exists; many Nigerian SMEs trade '
                        'through Instagram and WhatsApp rather than email, so Instagram is often the '
                        'most reliable way in.'),
    ('Data source', ' / '.join(sources) if sources else 'Google Maps'),
    ('Important caveat on scores', 'Apify credit covered a full delivery/contact check on the top '
                  '142 businesses only. Those show "Full" under Score basis. The rest were scored on '
                  'reviews, website, chain status, category and rating alone - they could not earn the '
                  '55 points tied to delivery, catering and takeout signals. So a low score on a "Basic" '
                  'row is a floor, not a verdict: it may simply be unchecked. Re-run enrichment on the '
                  'next tier when credit allows.'),
    ('Honest limitations', 'Delivery capability is inferred, not confirmed. Google\'s delivery flag is '
                           'self-reported and patchy in Nigeria, so a "No" is weak evidence of absence. '
                           'Review counts proxy for footfall, not for delivery volume specifically. '
                           'Treat the score as a call order, and confirm actual volumes on the phone.'),
]
for i, (k, v) in enumerate(rows, start=3):
    ws.cell(row=i, column=1, value=k).font = bold
    ws.cell(row=i, column=1).fill = PatternFill('solid', fgColor=LIGHT)
    ws.cell(row=i, column=1).alignment = Alignment(vertical='top')
    c = ws.cell(row=i, column=2, value=v); c.font = body
    c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.merge_cells(start_row=i, start_column=2, end_row=i, end_column=5)
    ws.row_dimensions[i].height = 56
    ws.cell(row=i, column=1).border = box; c.border = box
widths(ws, [22, 30, 24, 24, 24])

del wb['Sheet']
wb._sheets = [wb[n] for n in ['DASHBOARD', 'README', 'TARGET LIST', 'SCORING METHOD']]
OUT = '/mnt/user-data/outputs/Lagos_Delivery_Prospects.xlsx'
os.makedirs('/mnt/user-data/outputs', exist_ok=True)
wb.save(OUT)
print('saved', OUT, '| prospects', N)
print('bands:', collections.Counter(r['band'] for r in recs))
print('areas:', collections.Counter(r['area'] for r in recs))
