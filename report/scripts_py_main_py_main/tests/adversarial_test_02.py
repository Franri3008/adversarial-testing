import pytest

def test_main(main, capsys, monkeypatch):
    # Normal invocation: correct stdout, no stderr, returns None
    result = main()
    captured = capsys.readouterr()
    assert captured.out == "Hello from honcpiler!\n"
    assert captured.err == ""
    assert result is None

    # Environment variable must not affect output (catches r1_env_based_message)
    monkeypatch.setenv("HONCPILER_MESSAGE", "Hacked!")
    result = main()
    captured = capsys.readouterr()
    assert captured.out == "Hello from honcpiler!\n"
    assert captured.err == ""
    assert result is None

    # Calling with an argument must raise TypeError (catches r1_extra_branch_on_args)
    with pytest.raises(TypeError):
        main("unexpected_arg")