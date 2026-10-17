"""Git history -> commits (who changed what, when). Read-only: ``git log`` on a clone we just made."""
from __future__ import annotations

import hashlib
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .limits import MAX_COMMITS

BOT = re.compile(r"\[bot\]|dependabot|renovate|github-actions|greenkeeper|snyk-bot|pre-commit-ci", re.I)
SEP = "\x1e"
FS = "\x1f"


@dataclass
class Commit:
    sha: str
    author: str                       # canonical display name after identity resolution
    ts: int
    subject: str
    files: list[tuple[str, int]] = field(default_factory=list)       # (path, lines changed)
    email: str = ""                   # used only to merge aliases; never stored in the graph
    pid: str = ""                     # collision-free person id suffix


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "x"


def uid(text: str) -> str:
    """Stable, collision-free id suffix: readable slug + short hash (non-ASCII names slug to nothing)."""
    return f"{slug(text)[:40]}-{hashlib.sha1(text.encode()).hexdigest()[:6]}"


def read_history(repo: Path, limit: int = MAX_COMMITS) -> list[Commit]:
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "HOME": "/nonexistent", "GIT_TERMINAL_PROMPT": "0"}
    cmd = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "--no-pager", "-C", str(repo), "log",
           "--no-merges", "--no-renames", f"-n{limit}", "--numstat", f"--format={SEP}%H{FS}%an{FS}%ae{FS}%at{FS}%s"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env, errors="replace").stdout
    except (subprocess.TimeoutExpired, OSError):
        return []
    commits: list[Commit] = []
    for block in out.split(SEP)[1:]:
        head, _, rest = block.partition("\n")
        parts = head.split(FS, 4)
        if len(parts) < 5 or not parts[3].isdigit():
            continue
        sha, author, email, ts, subject = parts
        c = Commit(sha, author.strip(), int(ts), subject.strip()[:140], email=email.strip().lower())
        for ln in rest.splitlines():
            cols = ln.split("\t")
            if len(cols) == 3:
                a = int(cols[0]) if cols[0].isdigit() else 0
                d = int(cols[1]) if cols[1].isdigit() else 0
                c.files.append((cols[2], a + d))
        commits.append(c)
    resolve_identities(commits)
    return commits


def _identity_key(c: Commit) -> str:
    e = c.email
    if e.endswith("@users.noreply.github.com"):
        local = e.split("@")[0]
        return "gh:" + local.split("+")[-1]
    return e or "name:" + c.author.lower()


def resolve_identities(commits: list[Commit]) -> None:
    """Merge the same person across name spellings via (hashed-only) email; give every person a unique display name + id."""
    names: dict[str, Counter] = defaultdict(Counter)
    for c in commits:
        names[_identity_key(c)][c.author] += 1
    display: dict[str, str] = {}
    used: Counter = Counter()
    for key, cnt in sorted(names.items(), key=lambda kv: -sum(kv[1].values())):
        name = cnt.most_common(1)[0][0]
        used[name] += 1
        display[key] = name if used[name] == 1 else f"{name} #{used[name]}"
    for c in commits:
        key = _identity_key(c)
        c.author, c.pid = display[key], uid(key)
    for c in commits:
        c.email = ""                                          # drop raw emails as soon as identities are resolved


def head_sha(repo: Path) -> str:
    """The commit that was analysed, so the analysis can be reproduced exactly."""
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": "/nonexistent"}
    try:
        out = subprocess.run(["git", "--no-pager", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=15, env=env).stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return out if re.fullmatch(r"[0-9a-f]{40}", out) else ""


def is_bot(name: str) -> bool:
    return bool(BOT.search(name))


def module_stats(commits: list[Commit], module_of, modules: set[str], now: int) -> dict[str, dict]:
    """Per-module commit counts, authors, 90-day churn and top-author share (materialised on Service nodes)."""
    cut = now - 90 * 86400
    stats: dict[str, dict] = {m: {"commits": 0, "churn_90d": 0, "authors": Counter(), "last_ts": 0} for m in modules}
    for c in commits:
        if is_bot(c.author):
            continue
        touched: dict[str, int] = defaultdict(int)
        for path, lines in c.files:
            m = module_of(path)
            if m in stats:
                touched[m] += lines
        for m, lines in touched.items():
            s = stats[m]
            s["commits"] += 1
            s["authors"][c.author] += 1
            s["last_ts"] = max(s["last_ts"], c.ts)
            if c.ts >= cut:
                s["churn_90d"] += lines
    for s in stats.values():
        if s["commits"]:
            top, n = s["authors"].most_common(1)[0]
            s["top_author"], s["top_author_share"] = top, round(n / s["commits"], 3)
        else:
            s["top_author"], s["top_author_share"] = "", 0.0
    return stats
