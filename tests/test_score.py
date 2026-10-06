"""SPEC §6.4 - the nested additionalInfo shape once silently zeroed every delivery score."""
from lagosdata import score as S
from lagosdata.record import Business

NESTED = {'title': 'Fixture Kitchen', 'categoryName': 'Restaurant',
          'additionalInfo': {'Service options': [{'Delivery': True}, {'Takeout': True}],
                             'Dining options': [{'Catering': True}]}}


def test_flag_reads_nested_shape():
    assert S._flag(NESTED, 'additionalInfo.Service options.Delivery') is True
    assert S._flag(NESTED, 'additionalInfo.Dining options.Catering') is True
    assert S._flag(NESTED, 'additionalInfo.Service options.No-contact delivery') is False


def test_flag_reads_flattened_shape():
    flat = {'additionalInfo.Service options.Delivery': True}
    assert S._flag(flat, 'additionalInfo.Service options.Delivery') is True
    assert S._flag({'additionalInfo.Service options.Delivery': 'No'}, 'additionalInfo.Service options.Delivery') is False


def test_nested_signals_score():
    total, c, cat = S.score(NESTED, {})
    assert c['Google Delivery flag'] == 25 and c['Takeout'] == 5 and c['Catering offered'] == 15
    assert cat == 'Restaurant / Food'
    assert total == 25 + 5 + 15 + 6


def test_bands():
    assert S.band(60).startswith('Hot') and S.band(59.9).startswith('Warm')
    assert S.band(40).startswith('Warm') and S.band(25).startswith('Cool') and S.band(24.9).startswith('Cold')


def test_business_adapter_keeps_nested_path_live():
    b = Business(name='Fixture Mart', label='Supermarket', reviews=150, rating=4.3, website='https://m.example',
                 additional_info={'Service options': [{'Delivery': True}]},
                 delivery_text_signals=['catering'])
    view = S.apify_view(b)
    total, c, cat = S.score(view, S.name_counts_for([b]))
    assert c['Google Delivery flag'] == 25
    assert c['Catering offered'] == 15          # from website text, injected in the nested shape
    assert c['Has website'] == 8 and c['Rating 4.0+'] == 5 and c['Category weight'] == 10
    assert cat == 'Supermarket / Grocery'


def test_chain_by_name_frequency():
    bs = [Business(name='Fixture Pharmacy'), Business(name='Fixture Pharmacy')]
    total, c, _ = S.score(S.apify_view(bs[0]), S.name_counts_for(bs))
    assert c['Chain / multi-branch'] == 10
