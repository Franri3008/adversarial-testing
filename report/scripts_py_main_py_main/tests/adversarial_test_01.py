def test_main_mutations(main):
    # Call the main function and capture output
    import io
    import sys
    captured_output = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = captured_output
    main()
    sys.stdout = original_stdout
    output = captured_output.getvalue().strip()

    # Assertions to detect each mutation
    assert output == "Hello from honcpiler!", "Wrong string constant: expected 'Hello from honcpiler!'"
    assert "!" in output, "Missing exclamation: expected exclamation mark at the end"
    assert "honcpiler" in output, "Typo in name: expected 'honcpiler' in output"
    assert len(output) > 0, "No print: expected some output to be printed"
    assert not output.startswith(" "), "Extra whitespace: expected no leading space"