"""Bağımlılık listesi: requirements.txt ile pyproject.toml aynı paketleri içermeli."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib Python 3.11+")
def test_requirements_match_pyproject():
    import tomllib
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    req = [ln.strip() for ln in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
           if ln.strip() and not ln.startswith("#") and not ln.startswith("-e")]
    assert req == pyproject


def test_version_single_source():
    init = (ROOT / "trendpipe/__init__.py").read_text(encoding="utf-8")
    assert re.search(r'__version__ = "\d+\.\d+\.\d+"', init)
    assert 'dynamic = ["version"]' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
