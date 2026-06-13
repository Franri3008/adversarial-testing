import pytest

def test_main_behavior(main):
    # Capture the printed output
    import io
    import sys
    captured_output = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = captured_output
    try:
        main()
    finally:
        sys.stdout = original_stdout
    
    output = captured_output.getvalue().strip()
    
    # Assertions to detect the specified bugs
    assert output == "Hello from honcpiler!", "Output must match the expected greeting exactly"
    assert "Hello" in output, "Greeting must start with 'Hello'"
    assert "honcpiler" in output, "Program name 'honcpiler' must be present"
    assert "!" in output, "Exclamation mark must be present at the end"
    assert output[0].isupper(), "First letter of the greeting must be uppercase"