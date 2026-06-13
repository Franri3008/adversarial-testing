"""Acquire parsers: repo URL parsing, language inference, JSON-array extraction."""
import pytest

import acquire


def test_parse_repo_variants():
    assert acquire._parse_repo("https://github.com/NVIDIA/NemoClaw") == "NVIDIA/NemoClaw"
    assert acquire._parse_repo("https://github.com/NVIDIA/NemoClaw.git") == "NVIDIA/NemoClaw"
    assert acquire._parse_repo("git@github.com:NVIDIA/NemoClaw.git") == "NVIDIA/NemoClaw"
    assert acquire._parse_repo("NVIDIA/NemoClaw") == "NVIDIA/NemoClaw"


def test_parse_repo_invalid():
    with pytest.raises(ValueError):
        acquire._parse_repo("not a repo at all")


def test_language_for():
    assert acquire._language_for("src/x.py") == "python"
    assert acquire._language_for("src/x.ts") == "typescript"
    assert acquire._language_for("src/x.tsx") == "typescript"
    with pytest.raises(ValueError):
        acquire._language_for("src/Main.java")


def test_extract_json_array():
    assert acquire._extract_json_array('[{"id": "a"}]') == [{"id": "a"}]
    # embedded in prose / fences
    assert acquire._extract_json_array('here you go:\n```\n[{"id": "b"}]\n```') == [{"id": "b"}]
    with pytest.raises(ValueError):
        acquire._extract_json_array("no array here")
