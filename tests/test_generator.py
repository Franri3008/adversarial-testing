"""Generator helpers: code-block extraction and function-name inference."""
import generator


def test_extract_code_fenced_with_lang():
    text = "Sure:\n```python\ndef test_x():\n    assert True\n```\n"
    assert generator._extract_code(text) == "def test_x():\n    assert True"


def test_extract_code_fenced_no_lang():
    text = "```\nhello()\n```"
    assert generator._extract_code(text) == "hello()"


def test_extract_code_raw_fallback():
    assert generator._extract_code("no fences here") == "no fences here"


def test_python_function_name():
    assert generator._python_function_name("def merge_intervals(xs):\n    pass\n") == "merge_intervals"
    assert generator._python_function_name("x = 1\n") == "subject"


def test_ts_function_name():
    assert generator._ts_function_name("anything", "given") == "given"
    assert generator._ts_function_name("export function parseDuration(s) {}", None) == "parseDuration"
    assert generator._ts_function_name("const x = 1;", None) == "subject"
