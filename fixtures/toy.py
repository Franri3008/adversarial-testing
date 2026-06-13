REFERENCE_SRC = '''def merge_intervals(intervals):
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        last = merged[-1]
        if start <= last[1]:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return merged
'''

MUTANTS = [
    {
        "id": "M1_no_sort",
        "description": "Skips sorting, so unsorted input fails to merge.",
        "src": '''def merge_intervals(intervals):
    if not intervals:
        return []
    ordered = list(intervals)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        last = merged[-1]
        if start <= last[1]:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return merged
''',
    },
    {
        "id": "M2_strict_overlap",
        "description": "Uses strict < instead of <=, so touching intervals are not merged.",
        "src": '''def merge_intervals(intervals):
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        last = merged[-1]
        if start < last[1]:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return merged
''',
    },
    {
        "id": "M3_overwrite_end",
        "description": "Overwrites end instead of taking max, breaking nested intervals.",
        "src": '''def merge_intervals(intervals):
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        last = merged[-1]
        if start <= last[1]:
            last[1] = end
        else:
            merged.append([start, end])
    return merged
''',
    },
    {
        "id": "M4_drop_last",
        "description": "Drops the final accumulated interval.",
        "src": '''def merge_intervals(intervals):
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        last = merged[-1]
        if start <= last[1]:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return merged[:-1]
''',
    },
    {
        "id": "M5_empty_returns_none",
        "description": "Returns None instead of [] on empty input.",
        "src": '''def merge_intervals(intervals):
    if not intervals:
        return None
    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        last = merged[-1]
        if start <= last[1]:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return merged
''',
    },
]
