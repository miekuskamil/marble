"""Checks for docs/overview.html, the one-page project overview (no browser needed)."""
import pathlib
import re

PAGE = (pathlib.Path(__file__).resolve().parent.parent / "docs" / "overview.html").read_text()


def test_overview_has_no_scripts_or_external_assets():
    assert "<script" not in PAGE
    hosts = set(re.findall(r'(?:href|src)="https?://([^/"]+)', PAGE))
    assert hosts <= {"fonts.googleapis.com", "fonts.gstatic.com"}


def test_overview_svg_markers_are_defined():
    used = set(re.findall(r"url\(#([\w-]+)\)", PAGE))
    defined = set(re.findall(r'<marker id="([\w-]+)"', PAGE))
    assert used and used <= defined


def test_overview_supports_both_themes_and_one_open_phase():
    assert "prefers-color-scheme:light" in PAGE and ':root[data-theme="light"]' in PAGE
    assert PAGE.count('<details class="pc') == 6
    assert PAGE.count('name="phase" open') == 1
