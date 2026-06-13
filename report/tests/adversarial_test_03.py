def test_nested_interval_keeps_max_end(merge_intervals):
    assert merge_intervals([[1, 5], [2, 3]]) == [[1, 5]]