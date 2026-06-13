def test_touching_intervals_merge(merge_intervals):
    assert merge_intervals([[1, 2], [2, 3]]) == [[1, 3]]