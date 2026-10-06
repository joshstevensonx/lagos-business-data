from lagosdata.state import State


def test_done_searches_are_skipped_and_running_resets(tmp_path):
    st = State(tmp_path / 's.sqlite')
    st.start('osm', 't', 'a'); st.finish('osm', 't', 'a', 5)
    st.start('osm', 't2', 'a')                      # process dies mid-search
    st.close()
    st = State(tmp_path / 's.sqlite')
    assert st.is_done('osm', 't', 'a')
    assert not st.is_done('osm', 't2', 'a')
    assert {s['term']: s['status'] for s in st.searches()}['t2'] == 'pending'
    assert st.force(terms=['t']) == 1 and not st.is_done('osm', 't', 'a')
