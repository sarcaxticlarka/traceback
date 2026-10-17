# AI usage disclosure

Graph Hacks rule 11 requires disclosing AI coding assistants.

**Assistant:** Claude Code (Anthropic, model Claude Sonnet 5.5) wrote the first implementation of this repository
in a single working session at the participant's direction: the synthetic-company generator, graph tools, verifier,
memory/task layers, agents, evaluation harness, API, MCP server, React console, tests and documentation.

**Verification performed**
- 32 automated tests (verifier adversarial cases, 5/5 root-cause accuracy on planted alerts, handoff and atomic-claim
  behaviour, tenant isolation, MCP client round-trip, LLM paths with a scripted fake client).
- Evaluation ground truth is computed from the generator's model, independently of FalkorDB.
- Bugs found by running it rather than by reading it: the benchmark exposed FalkorDB's queue limit (added admission
  control and retries) and a concurrency race that made exact-count claims go stale (made counter claims monotone).

**Participant contribution** *(participant: complete this before submitting, rules 12–13)*
- [ ] I have read the graph model ([docs/DATA_MODEL.md](docs/DATA_MODEL.md)) and can explain every node/edge.
- [ ] I can explain each query in [QUERIES.md](QUERIES.md) and why it is shaped as it is.
- [ ] I can explain the verifier's five rules and the monotone-counter decision.
- [ ] I can explain the evaluation design, its limits, and why the graph agent's 100% is a correctness check.
- [ ] Describe here what you changed, chose or decided: …

The Claude planner path (`ANTHROPIC_API_KEY`) is implemented but was exercised only with a fake client in this build.
