"""Landing-page CSS must not leak into the app (a generic `.reveal` there once collapsed every graph node to the origin)."""
import re
from pathlib import Path

STYLES = Path(__file__).resolve().parent.parent / "web" / "src" / "styles"


def _classes(css: str) -> set[str]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return set(re.findall(r"\.([A-Za-z_][\w-]*)", re.sub(r"\{[^{}]*\}", "{}", css)))


def _selectors(css: str):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@media[^{]*\{", "", css)                      # flatten media blocks
    for m in re.finditer(r"(?m)^\s*([^@{}\n][^{}]*)\{", css):
        yield from (s.strip() for s in m.group(1).split(","))


def test_unscoped_landing_selectors_do_not_reuse_app_class_names():
    app_classes = _classes((STYLES / "components.css").read_text()) | _classes((STYLES / "app.css").read_text())
    clashes = []
    for sel in _selectors((STYLES / "landing.css").read_text()):
        if not sel or sel.startswith((".lp", ":root", "html", "body", "*", "from", "to")) or re.match(r"^\d+%", sel):
            continue
        first = re.match(r"\.([A-Za-z_][\w-]*)", sel)
        if first and first.group(1) in app_classes:
            clashes.append(sel)
    assert not clashes, f"landing.css rules that would also hit app elements: {clashes}"


def test_graph_animation_classes_are_namespaced():
    gv = (STYLES.parent / "components" / "GraphView.jsx").read_text()
    assert "'reveal'" not in gv and "g-reveal" in gv
