def test_main(main, capsys):
    main()
    captured = capsys.readouterr()
    assert captured.out == "Hello from honcpiler!\n"
    assert not captured.out.startswith(" ")
    assert captured.out[0] == "H"
    assert captured.out.lstrip() == captured.out