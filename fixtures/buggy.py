REFERENCE_SRC = '''def grade(score, total):
    if total <= 0:
        return 0.0
    ratio = score / total
    if ratio < 0:
        ratio = 0.0
    if ratio > 1:
        ratio = 1.0
    return round(ratio * 100, 2)
'''

BUGGY_SRC = '''def grade(score, total):
    ratio = score / total
    return round(ratio * 100, 2)
'''

_FIX_AFTER_B1 = '''def grade(score, total):
    if total <= 0:
        return 0.0
    ratio = score / total
    return round(ratio * 100, 2)
'''

_FIX_AFTER_B2 = '''def grade(score, total):
    if total <= 0:
        return 0.0
    ratio = score / total
    if ratio > 1:
        ratio = 1.0
    return round(ratio * 100, 2)
'''

PLANTED_BUGS = [
    {
        "id": "B1_zero_total",
        "description": "grade divides by total without guarding total <= 0, so grade(5, 0) raises ZeroDivisionError instead of returning 0.0.",
        "target_name": "grade",
        "stub_test_src": '''def test_grade_zero_total(grade):
    assert grade(5, 0) == 0.0
''',
        "stub_fixed_src": _FIX_AFTER_B1,
    },
    {
        "id": "B2_clamp_high",
        "description": "grade never clamps the ratio to 1, so grade(150, 100) returns 150.0 instead of the maximum 100.0.",
        "target_name": "grade",
        "stub_test_src": '''def test_grade_clamps_high(grade):
    assert grade(150, 100) == 100.0
''',
        "stub_fixed_src": _FIX_AFTER_B2,
    },
    {
        "id": "B3_clamp_low",
        "description": "grade never clamps the ratio to 0, so grade(-5, 100) returns -5.0 instead of the minimum 0.0.",
        "target_name": "grade",
        "stub_test_src": '''def test_grade_clamps_low(grade):
    assert grade(-5, 100) == 0.0
''',
        "stub_fixed_src": REFERENCE_SRC,
    },
]

MUTANTS = [
    {
        "id": "M_no_guard",
        "description": "grade drops the total <= 0 guard.",
        "src": '''def grade(score, total):
    ratio = score / total
    if ratio < 0:
        ratio = 0.0
    if ratio > 1:
        ratio = 1.0
    return round(ratio * 100, 2)
''',
    },
    {
        "id": "M_no_high",
        "description": "grade drops the upper clamp.",
        "src": '''def grade(score, total):
    if total <= 0:
        return 0.0
    ratio = score / total
    if ratio < 0:
        ratio = 0.0
    return round(ratio * 100, 2)
''',
    },
    {
        "id": "M_no_low",
        "description": "grade drops the lower clamp.",
        "src": '''def grade(score, total):
    if total <= 0:
        return 0.0
    ratio = score / total
    if ratio > 1:
        ratio = 1.0
    return round(ratio * 100, 2)
''',
    },
]
