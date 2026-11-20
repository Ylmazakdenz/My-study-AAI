"""Ayar dosyası doğrulaması: yazım hataları sessizce geçmemeli."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from trendpipe.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]


def _write(tmp_path, cfg):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return p


def _base():
    return yaml.safe_load((ROOT / "config/config.yaml").read_text(encoding="utf-8"))


def test_default_config_is_valid():
    cfg = load_config(ROOT / "config/config.yaml")
    assert cfg["sources"]["google_trends"]["type"] == "google_trends"
    assert cfg["window"]["yoy"] is True


@pytest.mark.parametrize("mutate, expected", [
    (lambda c: c["window"].update(recent_day=28), "window.recent_day: bilinmeyen alan"),
    (lambda c: c["window"].update(recent_days=1), "window.recent_days"),
    (lambda c: c["sources"]["google_trends"].update(geoo="TR"), "bilinmeyen ayar: geoo"),
    (lambda c: c["sources"]["wikimedia"].update(type="wikipedia"), "tipi bilinmiyor"),
    (lambda c: c["terms"][0]["queries"].update(googletrends="x"), "tanımsız kaynak adı: googletrends"),
    (lambda c: c["terms"].append(dict(c["terms"][0])), "Tekrarlanan terim id"),
    (lambda c: c["terms"][0].update(id="Trençkot"), "terms.0.id"),
    (lambda c: c["analysis"]["low_volume"].update(wiki=3), "low_volume içinde tanımsız"),
    (lambda c: c.pop("brand"), "brand: zorunlu alan eksik"),
])
def test_typos_are_rejected(tmp_path, mutate, expected):
    cfg = _base()
    mutate(cfg)
    with pytest.raises(ConfigError) as e:
        load_config(_write(tmp_path, cfg))
    assert expected in str(e.value)


@pytest.mark.parametrize("mutate, expected", [
    (lambda c: c["sources"]["google_trends"].update(samples="iki"), "'samples' geçersiz"),
    (lambda c: c["sources"]["google_trends"].update(samples=9), "'samples' geçersiz"),
    (lambda c: c["sources"]["google_trends"].update(geo="turkiye"), "'geo' geçersiz"),
    (lambda c: c["sources"]["wikimedia"].update(agent="users"), "'agent' geçersiz"),
    (lambda c: c["sources"]["wikimedia_en"].update(project="en.wiki"), "'project' geçersiz"),
])
def test_source_option_types_are_checked(tmp_path, mutate, expected):
    cfg = _base()
    mutate(cfg)
    with pytest.raises(ConfigError) as e:
        load_config(_write(tmp_path, cfg))
    assert expected in str(e.value)
