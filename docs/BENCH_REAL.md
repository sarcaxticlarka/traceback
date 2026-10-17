# Benchmark on real repositories

Each repo is cloned fresh (shallow), analysed, loaded into its own FalkorDB graph, and asked auto-generated questions whose ground truth comes from the static analyser's module model and the raw commit list (never from FalkorDB). The baseline retrieves 8 file chunks (hybrid dense+TF-IDF) and parses the imports in them.

| Repository | Files | Modules | Module deps | Commits | Questions | Graph exact | Docs-only exact | Grounded | Ingest |
|---|---|---|---|---|---|---|---|---|---|
| [pallets/click](https://github.com/pallets/click) | 91 | 18 | 17 | 1353 | 16 | 100% | 25% | 100% | 0.6 s |
| [psf/requests](https://github.com/psf/requests) | 37 | 6 | 3 | 1435 | 10 | 100% | 0% | 100% | 0.3 s |
| [expressjs/express](https://github.com/expressjs/express) | 141 | 38 | 29 | 1445 | 26 | 100% | 27% | 100% | 0.4 s |
| [spf13/cobra](https://github.com/spf13/cobra) | 36 | 2 | 1 | 964 | 3 | 100% | 0% | 100% | 0.3 s |
| [gin-gonic/gin](https://github.com/gin-gonic/gin) | 99 | 8 | 15 | 1375 | 25 | 100% | 0% | 100% | 0.3 s |
| [tiangolo/fastapi](https://github.com/tiangolo/fastapi) | 1172 | 97 | 160 | 619 | 30 | 100% | 10% | 100% | 4.4 s |
| **All** | | | | | **110** | **100%** | **13%** | | |
