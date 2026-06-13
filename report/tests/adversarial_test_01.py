def test_noop(merge_intervals):
    assert merge_intervals([[1,3]]) == [[1,3]]