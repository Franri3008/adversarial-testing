import pytest

def test_main_output(main, capsys):
    main()
    captured = capsys.readouterr()
    assert captured.out == "Hello from honcpiler!\n"