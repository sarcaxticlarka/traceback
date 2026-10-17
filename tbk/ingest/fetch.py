"""Obtain a source tree safely: shallow git clone of a public GitHub repo, or a validated zip / folder upload."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

from .limits import CLONE_DEPTH, CLONE_TIMEOUT_S, MAX_FILES, MAX_TREE_BYTES, MAX_UPLOAD_BYTES

GITHUB = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


class IngestError(ValueError):
    """A user-facing problem with the submitted source (bad URL, too large, unsafe archive)."""


def parse_github_url(url: str) -> tuple[str, str]:
    m = GITHUB.match(url.strip())
    if not m:
        raise IngestError("Only public repositories of the form https://github.com/<owner>/<repo> are supported.")
    return m.group(1), m.group(2)


def tree_size(root: Path) -> tuple[int, int]:
    total = files = 0
    for dp, _, fns in os.walk(root, followlinks=False):
        if ".git" in Path(dp).parts:
            continue
        for fn in fns:
            files += 1
            try:
                total += (Path(dp) / fn).lstat().st_size
            except OSError:
                pass
    return total, files


def clone_github(url: str, dest: Path, depth: int = CLONE_DEPTH) -> tuple[str, str]:
    owner, repo = parse_github_url(url)
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": "/nonexistent", "GIT_TERMINAL_PROMPT": "0",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    cmd = ["git", "-c", "protocol.allow=never", "-c", "protocol.https.allow=always", "-c", "core.symlinks=false",
           "-c", "core.hooksPath=/dev/null", "clone", "--depth", str(depth), "--no-tags", "--single-branch",
           "--no-recurse-submodules", "--quiet", f"https://github.com/{owner}/{repo}.git", str(dest)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=CLONE_TIMEOUT_S, env=env)
    except subprocess.TimeoutExpired:
        shutil.rmtree(dest, ignore_errors=True)
        raise IngestError(f"Cloning took longer than {CLONE_TIMEOUT_S}s. Try a smaller repository.") from None
    if r.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        msg = (r.stderr or "").strip().splitlines()[-1:] or ["clone failed"]
        raise IngestError(f"Could not clone {owner}/{repo} (is it public?): {msg[0][:160]}")
    size, files = tree_size(dest)
    if size > MAX_TREE_BYTES or files > MAX_FILES * 2:
        shutil.rmtree(dest, ignore_errors=True)
        raise IngestError(f"Repository is too large for the public demo ({size // 1_000_000} MB, {files} files).")
    return owner, repo


def _safe_rel(name: str) -> str | None:
    name = name.replace("\\", "/").lstrip("/")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts or ".." in parts or parts[0] == ".git" or ".git" in parts:
        return None
    return "/".join(parts)


def extract_zip(data: bytes, dest: Path) -> int:
    """Extract a zip with zip-slip, symlink, size and count protection. Returns number of files written."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise IngestError(f"Upload exceeds {MAX_UPLOAD_BYTES // 1_000_000} MB.")
    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile:
        raise IngestError("That file is not a valid zip archive.") from None
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_FILES * 2 or sum(i.file_size for i in infos) > MAX_TREE_BYTES:
        raise IngestError("Archive is too large (file count or uncompressed size).")
    # strip a single top-level folder (zip of a directory)
    tops = {i.filename.split("/", 1)[0] for i in infos if "/" in i.filename}
    strip = len(tops) == 1 and all("/" in i.filename for i in infos)
    n = 0
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    for i in infos:
        if (i.external_attr >> 16) & 0o170000 == 0o120000:         # symlink
            continue
        name = i.filename.split("/", 1)[1] if strip else i.filename
        rel = _safe_rel(name)
        if rel is None:
            continue
        target = (dest / rel).resolve()
        if root not in target.parents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(i) as src, open(target, "wb") as out:
            out.write(src.read(MAX_TREE_BYTES + 1)[:MAX_TREE_BYTES])
        n += 1
    if n == 0:
        raise IngestError("The archive contained no usable files.")
    return n


def write_uploaded_files(files: list[tuple[str, bytes]], dest: Path) -> int:
    total = sum(len(b) for _, b in files)
    if total > MAX_UPLOAD_BYTES or len(files) > MAX_FILES * 2:
        raise IngestError("Upload is too large (size or file count).")
    names = [f[0].replace("\\", "/") for f in files]
    top = {n.split("/", 1)[0] for n in names if "/" in n}
    strip = len(top) == 1 and all("/" in n for n in names)
    dest.mkdir(parents=True, exist_ok=True)
    root, n = dest.resolve(), 0
    for (name, data), orig in zip(files, names):
        rel = _safe_rel(orig.split("/", 1)[1] if strip else orig)
        if rel is None:
            continue
        target = (dest / rel).resolve()
        if root not in target.parents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        n += 1
    if n == 0:
        raise IngestError("No usable files in the upload.")
    return n
