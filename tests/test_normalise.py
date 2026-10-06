from lagosdata.normalise import is_poi, norm_addr, norm_name, street_of


def test_norm_name_strips_company_words():
    assert norm_name('Medplus Pharmacy Nigeria Ltd') == norm_name('MEDPLUS PHARMACY')
    assert norm_name('The Fixture Ventures & Global Services') == 'fixture'


def test_norm_addr_strips_street_words():
    assert norm_addr('No 5, Fixture Road') == norm_addr('5 Fixture Rd')


def test_street_of():
    assert street_of('Shop 4 12 Ikorodu Road, Anthony') == '12 Ikorodu Road'
    assert street_of('19c Sylvia Cres, Anthony, Lagos') == '19c Sylvia Cres'


def test_poi_filter_needs_empty_label():
    assert is_poi({'name': 'Iyana Oworo (Car Wash) Bus Stop', 'label': ''})
    assert is_poi({'name': 'Sylvia Crescent', 'label': ''})
    assert not is_poi({'name': 'Bus Stop Pharmacy', 'label': 'Pharmacy'})
    assert not is_poi({'name': 'Roundabout Grill', 'label': 'Restaurant'})
