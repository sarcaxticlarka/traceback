"""Static analysis of a source tree: files, languages, internal imports, modules.

Nothing here executes repository code. Python is parsed with ``ast`` (which does not import or run it); the other
languages use conservative regexes. Only imports that resolve to files *inside the repository* become dependencies.
"""
from __future__ import annotations

import ast
import json
import os
import posixpath
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .limits import (CORPUS_CHARS, CORPUS_FILES, DOC_CHARS, MAX_DOCS, MAX_FILES, MAX_MODULES, MAX_PARSE_BYTES,
                     MAX_TREE_BYTES, SKIP_DIRS)

LANG = {".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".go": "go", ".java": "java", ".kt": "kotlin", ".rs": "rust",
        ".rb": "ruby", ".php": "php", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp",
        ".swift": "swift", ".scala": "scala", ".vue": "vue", ".svelte": "svelte"}
DOC_EXT = {".md", ".rst", ".txt", ".adoc"}
JS_EXT = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte"]

_JS_IMPORT = re.compile(r"""(?:import|export)\s+(?:[^'"`;]*?\s+from\s+)?['"]([^'"\n]+)['"]|require\(\s*['"]([^'"\n]+)['"]\s*\)|import\(\s*['"]([^'"\n]+)['"]\s*\)""")
_GO_IMPORT_BLOCK = re.compile(r'import\s*\((.*?)\)', re.S)
_GO_IMPORT_ONE = re.compile(r'import\s+(?:[\w.]+\s+)?"([^"]+)"')
_GO_QUOTED = re.compile(r'"([^"]+)"')
_JAVA_PKG = re.compile(r"^\s*package\s+([\w.]+)", re.M)
_JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+(?:\.\*)?)", re.M)
_C_INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)


@dataclass
class FileInfo:
    path: str
    lang: str
    loc: int
    size: int


@dataclass
class RepoModel:
    root: str = ""
    files: dict[str, FileInfo] = field(default_factory=dict)
    module_depth: int = 1
    modules: dict[str, dict] = field(default_factory=dict)          # name -> {files, loc, langs}
    deps: dict[tuple[str, str], dict] = field(default_factory=dict)  # (src,dst) -> {count, sites}
    file_deps: int = 0
    docs: list[dict] = field(default_factory=list)                   # {path, title, body, kind}
    corpus: list[dict] = field(default_factory=list)                 # {path, text}  (docs-only baseline)
    codeowners: str | None = None
    codeowners_path: str | None = None
    skipped: Counter = field(default_factory=Counter)

    def module_of(self, path: str) -> str | None:
        return module_name(path, self.module_depth)

    def to_json(self) -> dict:
        return {"module_depth": self.module_depth,
                "modules": self.modules,
                "deps": [{"src": a, "dst": b, **v} for (a, b), v in self.deps.items()],
                "files": {p: {"lang": f.lang, "loc": f.loc} for p, f in self.files.items()}}


def module_name(path: str, depth: int) -> str:
    parts = path.split("/")[:-1]
    if not parts:
        return "./"
    return "/".join(parts[:depth]) + "/"


# ----------------------------------------------------------------------------------------------- walk
def _is_text(sample: bytes) -> bool:
    return b"\x00" not in sample


def walk_tree(root: Path) -> RepoModel:
    m = RepoModel(root=str(root))
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".") or d in (".github",))
        for fn in sorted(filenames):
            full = Path(dirpath) / fn
            rel = full.relative_to(root).as_posix()
            if full.is_symlink():
                m.skipped["symlink"] += 1
                continue
            try:
                size = full.stat().st_size
            except OSError:
                continue
            total += size
            if len(m.files) >= MAX_FILES or total > MAX_TREE_BYTES:
                m.skipped["limit"] += 1
                continue
            ext = Path(fn).suffix.lower()
            low = fn.lower()
            if low in ("codeowners",) or rel.lower().endswith(("/codeowners",)) or rel.lower() == "codeowners":
                if m.codeowners is None and size < 200_000:
                    m.codeowners, m.codeowners_path = full.read_text("utf-8", "ignore"), rel
                continue
            lang = LANG.get(ext)
            if lang is None and ext not in DOC_EXT:
                continue
            if size > MAX_PARSE_BYTES * 5:
                m.skipped["large"] += 1
                continue
            try:
                head = full.read_bytes()[: MAX_PARSE_BYTES]
            except OSError:
                continue
            if not _is_text(head[:2000]):
                m.skipped["binary"] += 1
                continue
            text = head.decode("utf-8", "ignore")
            if lang:
                m.files[rel] = FileInfo(rel, lang, text.count("\n") + 1, size)
            else:
                if len(m.docs) < MAX_DOCS:
                    title = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.strip()), rel)[:140]
                    m.docs.append({"path": rel, "title": title, "body": text[:DOC_CHARS], "kind": _doc_kind(rel)})
            if len(m.corpus) < CORPUS_FILES:
                m.corpus.append({"path": rel, "text": text[: (DOC_CHARS if not lang else CORPUS_CHARS)]})
    return m


def _doc_kind(path: str) -> str:
    low = path.lower()
    if re.search(r"(^|/)(adr|adrs|decisions?|rfcs?)(/|$)", low):
        return "adr"
    if low.endswith(("readme.md", "readme.rst", "readme.txt")):
        return "readme"
    return "doc"


# ----------------------------------------------------------------------------------------------- imports
def extract_imports(m: RepoModel, only: set[str] | None = None, texts: dict[str, str] | None = None) -> list[tuple[str, str, int]]:
    """Return (src_file, dst_file_or_pseudo_path, line) for imports that resolve inside the repo."""
    root = Path(m.root)
    paths = set(m.files)
    py_idx: dict[str, list[str]] = defaultdict(list)
    java_idx: dict[str, str] = {}
    java_pkg: dict[str, list[str]] = defaultdict(list)
    by_base: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        by_base[posixpath.basename(p)].append(p)
        if p.endswith(".py"):
            parts = p[:-3].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            for i in range(len(parts)):
                py_idx[".".join(parts[i:])].append(p)
    go_mod, js_pkgs = _go_module(root), _js_packages(root, paths)
    src_texts: dict[str, str] = {}

    def text_of(p: str) -> str:
        if texts is not None and p in texts:
            return texts[p]
        if p not in src_texts:
            try:
                src_texts[p] = (root / p).read_text("utf-8", "ignore")[:MAX_PARSE_BYTES]
            except OSError:
                src_texts[p] = ""
        return src_texts[p]

    for p, f in m.files.items():
        if f.lang in ("java", "kotlin"):
            t = text_of(p)
            pk = _JAVA_PKG.search(t)
            if pk:
                cls = posixpath.splitext(posixpath.basename(p))[0]
                java_idx[f"{pk.group(1)}.{cls}"] = p
                java_pkg[pk.group(1)].append(p)

    out: list[tuple[str, str, int]] = []
    for p, f in m.files.items():
        if only is not None and p not in only:
            continue
        t = text_of(p)
        if f.lang == "python":
            out += _py_imports(p, t, py_idx)
        elif f.lang in ("javascript", "typescript", "vue", "svelte"):
            out += _js_imports(p, t, paths, js_pkgs)
        elif f.lang == "go" and go_mod:
            out += _go_imports(p, t, go_mod, paths)
        elif f.lang in ("java", "kotlin"):
            out += _java_imports(p, t, java_idx, java_pkg)
        elif f.lang in ("c", "cpp"):
            out += _c_imports(p, t, paths, by_base)
    return out


def _py_imports(path: str, text: str, idx: dict[str, list[str]]) -> list[tuple[str, str, int]]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return []
    pkg = path.split("/")[:-1]
    out = []

    def resolve(dotted: str) -> str | None:
        parts = dotted.split(".")
        for k in range(len(parts), 0, -1):
            c = idx.get(".".join(parts[:k]))
            if c:
                return min(c, key=lambda x: (len(x), x))
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                t = resolve(a.name)
                if t and t != path:
                    out.append((path, t, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg[: len(pkg) - (node.level - 1)] if node.level - 1 <= len(pkg) else []
                mod = ".".join(base + (node.module.split(".") if node.module else []))
                cands = [f"{mod}.{a.name}" if mod else a.name for a in node.names] + ([mod] if mod else [])
                t = next((resolve_exact(idx, c) for c in cands if resolve_exact(idx, c)), None)
            else:
                mod = node.module or ""
                t = next((resolve(f"{mod}.{a.name}") for a in node.names if resolve(f"{mod}.{a.name}") and
                          resolve(f"{mod}.{a.name}") != resolve(mod)), None) or resolve(mod)
            if t and t != path:
                out.append((path, t, node.lineno))
    return out


def resolve_exact(idx: dict[str, list[str]], dotted: str) -> str | None:
    c = idx.get(dotted)
    return min(c, key=lambda x: (len(x), x)) if c else None


def _js_packages(root: Path, paths: set[str]) -> dict[str, str]:
    """Monorepo workspace packages: package name -> directory."""
    out = {}
    for p in sorted(x for x in paths if False):      # package.json is not a source file; scan separately
        pass
    for pj in list(root.glob("package.json")) + list(root.glob("*/package.json")) + list(root.glob("*/*/package.json")):
        try:
            name = json.loads(pj.read_text("utf-8", "ignore")).get("name")
        except (OSError, ValueError):
            continue
        if isinstance(name, str):
            out[name] = pj.parent.relative_to(root).as_posix().rstrip(".") or "."
    return out


def _js_imports(path: str, text: str, paths: set[str], pkgs: dict[str, str]) -> list[tuple[str, str, int]]:
    out = []
    here = posixpath.dirname(path)
    for mt in _JS_IMPORT.finditer(text):
        spec = next(g for g in mt.groups() if g)
        line = text.count("\n", 0, mt.start()) + 1
        target = None
        if spec.startswith("."):
            target = _js_resolve(posixpath.normpath(posixpath.join(here, spec)), paths)
        elif spec.startswith(("@/", "~/")):
            for base in ("src/", ""):
                target = _js_resolve(base + spec[2:], paths)
                if target:
                    break
        else:
            for name, d in pkgs.items():
                if spec == name or spec.startswith(name + "/"):
                    sub = spec[len(name):].lstrip("/")
                    cand = posixpath.normpath(posixpath.join(d, "src", sub)) if sub else None
                    target = (cand and _js_resolve(cand, paths)) or (_js_resolve(posixpath.join(d, sub), paths) if sub else None) \
                        or _first_in_dir(d, paths)
                    break
        if target and target != path:
            out.append((path, target, line))
    return out


def _js_resolve(base: str, paths: set[str]) -> str | None:
    if base in paths:
        return base
    for e in JS_EXT:
        if base + e in paths:
            return base + e
    for e in JS_EXT:
        if f"{base}/index{e}" in paths:
            return f"{base}/index{e}"
    return None


def _first_in_dir(d: str, paths: set[str]) -> str | None:
    pre = d.rstrip("/") + "/"
    return next((p for p in sorted(paths) if p.startswith(pre)), None)


def _go_module(root: Path) -> str | None:
    gm = root / "go.mod"
    if gm.exists():
        mt = re.search(r"^module\s+(\S+)", gm.read_text("utf-8", "ignore"), re.M)
        return mt.group(1) if mt else None
    return None


def _go_imports(path: str, text: str, mod: str, paths: set[str]) -> list[tuple[str, str, int]]:
    specs: list[tuple[str, int]] = []
    for blk in _GO_IMPORT_BLOCK.finditer(text):
        base = text.count("\n", 0, blk.start())
        for i, ln in enumerate(blk.group(1).splitlines()):
            mt = _GO_QUOTED.search(ln)
            if mt:
                specs.append((mt.group(1), base + i + 1))
    for mt in _GO_IMPORT_ONE.finditer(text):
        specs.append((mt.group(1), text.count("\n", 0, mt.start()) + 1))
    out = []
    for spec, line in specs:
        if spec == mod or spec.startswith(mod + "/"):
            d = spec[len(mod):].lstrip("/")
            pre = (d + "/") if d else ""
            target = next((p for p in sorted(paths) if p.endswith(".go") and posixpath.dirname(p) == d.rstrip("/")), None)
            if target and target != path and posixpath.dirname(target) != posixpath.dirname(path):
                out.append((path, target, line))
    return out


def _java_imports(path: str, text: str, idx: dict[str, str], pkg: dict[str, list[str]]) -> list[tuple[str, str, int]]:
    out = []
    for mt in _JAVA_IMPORT.finditer(text):
        name, line = mt.group(1), text.count("\n", 0, mt.start()) + 1
        t = None
        if name.endswith(".*"):
            files = pkg.get(name[:-2])
            t = files[0] if files else None
        else:
            parts = name.split(".")
            for k in range(len(parts), 1, -1):
                t = idx.get(".".join(parts[:k]))
                if t:
                    break
        if t and t != path:
            out.append((path, t, line))
    return out


def _c_imports(path: str, text: str, paths: set[str], by_base: dict[str, list[str]]) -> list[tuple[str, str, int]]:
    out = []
    here = posixpath.dirname(path)
    for mt in _C_INCLUDE.finditer(text):
        spec, line = mt.group(1), text.count("\n", 0, mt.start()) + 1
        cand = posixpath.normpath(posixpath.join(here, spec))
        t = cand if cand in paths else spec if spec in paths else None
        if t is None:
            hits = [p for p in by_base.get(posixpath.basename(spec), []) if p.endswith(spec)]
            t = hits[0] if len(hits) == 1 else None
        if t and t != path:
            out.append((path, t, line))
    return out


# ----------------------------------------------------------------------------------------------- modules
def choose_depth(paths: list[str]) -> int:
    best = 1
    for d in (1, 2, 3, 4):
        n = len({module_name(p, d) for p in paths})
        if n <= MAX_MODULES:
            best = d
    return best


def build_modules(m: RepoModel) -> RepoModel:
    m.module_depth = choose_depth(list(m.files))
    mods: dict[str, dict] = {}
    for p, f in m.files.items():
        mod = m.module_of(p)
        e = mods.setdefault(mod, {"files": 0, "loc": 0, "langs": Counter()})
        e["files"] += 1
        e["loc"] += f.loc
        e["langs"][f.lang] += 1
    m.modules = {k: {"files": v["files"], "loc": v["loc"], "langs": dict(v["langs"].most_common(3))} for k, v in sorted(mods.items())}
    imports = extract_imports(m)
    m.file_deps = len(imports)
    for src, dst, line in imports:
        a, b = m.module_of(src), m.module_of(dst)
        if a is None or b is None or a == b or a not in m.modules or b not in m.modules:
            continue
        e = m.deps.setdefault((a, b), {"count": 0, "sites": []})
        e["count"] += 1
        if len(e["sites"]) < 3:
            e["sites"].append(f"{src}:{line} → {dst}")
    return m


def analyze(root: Path) -> RepoModel:
    return build_modules(walk_tree(root))
