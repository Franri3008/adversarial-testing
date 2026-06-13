import inspect


def test_main_adversarial(main, capsys):
    # main must return None (catches r1_return_value_added)
    result = main()
    assert result is None

    # main must print exactly the expected line (catches r1_dead_branch_extra_print)
    captured = capsys.readouterr()
    assert captured.out == "Hello from honcpiler!\n"

    # main must take no parameters (catches r1_default_arg_unused)
    sig = inspect.signature(main)
    assert len(sig.parameters) == 0

    # Verify the source module uses the correct __main__ guard
    # (catches r1_guard_name_typo and r1_guard_swap_to_truthy_check)
    module = inspect.getmodule(main)
    source = inspect.getsource(module)
    assert 'if __name__ == "__main__":' in source or \
           "if __name__ == '__main__':" in source

    # No accidental whitespace-only or extra prints on a second call
    main()
    captured2 = capsys.readouterr()
    assert captured2.out == "Hello from honcpiler!\n"
    assert "  " not in captured2.out.replace("Hello from honcpiler!", "")