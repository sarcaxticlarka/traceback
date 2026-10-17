"""Resource limits for ingesting untrusted repositories. Everything is static analysis: no repo code is ever executed."""
import os

MAX_FILES = int(os.getenv("TBK_MAX_FILES", "25000"))
MAX_TREE_BYTES = int(os.getenv("TBK_MAX_TREE_MB", "250")) * 1_000_000        # uncompressed working tree
MAX_UPLOAD_BYTES = int(os.getenv("TBK_MAX_UPLOAD_MB", "100")) * 1_000_000
MAX_PARSE_BYTES = 400_000                                                    # skip huge/generated files when parsing
MAX_COMMITS = int(os.getenv("TBK_MAX_COMMITS", "1500"))
CLONE_DEPTH = int(os.getenv("TBK_CLONE_DEPTH", "1500"))
CLONE_TIMEOUT_S = int(os.getenv("TBK_CLONE_TIMEOUT", "150"))
MAX_MODULES = 120
MAX_DOCS = 300
DOC_CHARS = 6000
CORPUS_FILES = 5000                                                          # files kept for the docs-only baseline
CORPUS_CHARS = 1800
WORKSPACE_TTL_S = int(os.getenv("TBK_WORKSPACE_TTL_H", "12")) * 3600
MAX_WORKSPACES = int(os.getenv("TBK_MAX_WORKSPACES", "25"))
INGESTS_PER_HOUR = int(os.getenv("TBK_INGESTS_PER_HOUR", "8"))               # per client address

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "out", "target", "__pycache__", ".venv", "venv", "env",
             ".next", ".nuxt", ".cache", "coverage", ".tox", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
             "bower_components", "third_party", "site-packages", ".gradle", ".terraform"}
