def test_unsorted_input_merges(merge_intervals):
    assert merge_intervals([[2, 6], [1, 3]]) == [[1, 6]]