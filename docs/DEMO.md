# Demo script (≈3 min) and submission checklist

| Time | Show | Say |
|---|---|---|
| 0:00 | Console, alert list | "Agents guess when context is scattered. TRACEBACK keeps it in FalkorDB and won't say what it can't trace." |
| 0:15 | **Run the crew** on LIVE-1; evidence graph replays | "Track 1: tools chosen over MCP; each hop is a Cypher traversal." |
| 0:50 | Click a claim → its edges light up; **Inject hallucination** → withheld with reasons | "Every claim carries edge ids; the verifier drops what it can't re-confirm." |
| 1:15 | Handoff table, actions with risk and approval | "Track 2: agents coordinate only through Task nodes." |
| 1:35 | *Agent memory* tab → cold-start & re-learn | "Procedural memory: runbooks improve as outcomes write back." |
| 1:55 | Switch tenant; *Proof* → isolation test | "Same service names, separate graphs, zero leakage." |
| 2:10 | *Company brain*: "Which teams own services impacted if auth-service fails?" | "Track 3: 9 teams, sourced; docs-only finds 5." |
| 2:30 | *Proof* chart, then flip **FalkorDB graph: OFF** and re-run | "Rule 3 as an experiment: without the graph, 0% verifiable." |
| 2:50 | Repo + URL | "All queries and the data model are in the README." |

## Checklist
- [ ] Public repo, README renders · [ ] data model + QUERIES.md linked · [ ] demo video (public/unlisted)
- [ ] Live deployment URL or `docker compose up` · [ ] tracks named: Agents That Act on Connected Data, Agent Memory and Coordination, Company Brain
- [ ] AI_USAGE.md completed by the participant · [ ] blog post link · [ ] submit before Oct 18, 23:59 IST
