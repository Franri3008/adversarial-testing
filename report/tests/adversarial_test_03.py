def test_x(merge_intervals):
    assert merge_intervals([[2,6],[1,3]]) == [[1,6]]
    assert merge_intervals([[1,2],[2,3]]) == [[1,3]]
    assert merge_intervals([[1,5],[2,3]]) == [[1,5]]
    assert merge_intervals([[1,2]]) == [[1,2]]
    assert merge_intervals([]) == []