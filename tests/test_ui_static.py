"""Guards for the web UI: keep it compatible with the strict CSP and safe rendering."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name):
    return (STATIC / name).read_text(encoding="utf-8")


def test_html_has_no_inline_code_or_external_sources():
    html = read("index.html")
    assert "<style" not in html
    assert " style=" not in html
    assert not re.search(r"\son[a-z]+\s*=", html)          # no inline event handlers
    scripts = re.findall(r"<script\b[^>]*>", html)
    assert scripts and all('src="/static/' in s for s in scripts)
    assert not re.search(r"(src|href)=\"(https?:)?//", html)  # nothing from other origins


def test_js_never_renders_markup():
    js = read("app.js")
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert banned not in js, banned
    assert "localStorage" not in js and "sessionStorage" not in js  # token stays in memory


def test_css_loads_nothing_external():
    css = read("style.css")
    assert "@import" not in css
    assert not re.search(r"url\(\s*['\"]?(https?:)?//", css)
