REFERENCE_SRC = '''def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def mean(numbers):
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def running_max(numbers):
    result = []
    best = None
    for n in numbers:
        if best is None or n > best:
            best = n
        result.append(best)
    return result
'''

BUGGY_SRC = '''def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return value
    return value


def mean(numbers):
    return sum(numbers) / len(numbers)


def running_max(numbers):
    result = []
    best = None
    for n in numbers:
        if best is None or n < best:
            best = n
        result.append(best)
    return result
'''

PLANTED_BUGS = [
    {
        "id": "B1_clamp_upper",
        "description": "clamp returns the original value when it exceeds high instead of clamping to high.",
        "target_name": "clamp",
        "stub_test_src": '''def test_clamp_above_high():
    assert clamp(10, 0, 5) == 5
''',
    },
    {
        "id": "B2_mean_empty",
        "description": "mean raises ZeroDivisionError on an empty list instead of returning 0.0.",
        "target_name": "mean",
        "stub_test_src": '''def test_mean_empty():
    assert mean([]) == 0.0
''',
    },
    {
        "id": "B3_running_max_min",
        "description": "running_max uses < instead of >, so it tracks the running minimum rather than the maximum.",
        "target_name": "running_max",
        "stub_test_src": '''def test_running_max_tracks_max():
    assert running_max([1, 3, 2, 5, 4]) == [1, 3, 3, 5, 5]
''',
    },
]

MUTANTS = [
    {
        "id": "M_clamp_low",
        "description": "clamp ignores the lower bound.",
        "src": '''def clamp(value, low, high):
    if value > high:
        return high
    return value


def mean(numbers):
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def running_max(numbers):
    result = []
    best = None
    for n in numbers:
        if best is None or n > best:
            best = n
        result.append(best)
    return result
''',
    },
    {
        "id": "M_mean_off_by_one",
        "description": "mean divides by len(numbers) + 1.",
        "src": '''def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def mean(numbers):
    if not numbers:
        return 0.0
    return sum(numbers) / (len(numbers) + 1)


def running_max(numbers):
    result = []
    best = None
    for n in numbers:
        if best is None or n > best:
            best = n
        result.append(best)
    return result
''',
    },
    {
        "id": "M_running_max_first",
        "description": "running_max never updates best after the first element.",
        "src": '''def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def mean(numbers):
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def running_max(numbers):
    result = []
    best = None
    for n in numbers:
        if best is None:
            best = n
        result.append(best)
    return result
''',
    },
]
