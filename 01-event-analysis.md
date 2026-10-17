# 01 — Event Analysis (every detail, decoded)

## Facts

| Item | Value |
|---|---|
| Name | Graph Hacks: Context for AI Agents, powered by FalkorDB, run by WeMakeDevs |
| Window | Oct 15, 12:01 AM IST → Oct 18, 11:59 PM IST (2026) |
| Format | Online, worldwide, free |
| Team | Solo or up to 4; each person on one team only |
| Registered | ~7,652 (as of read). Expect a few hundred real submissions; most will be thin RAG wrappers |
| Prize pool | $20,000 total. One prize per track + 2 side prizes. **Every member of a winning team gets the prize** |
| Track 1 prize | iPhone 18 Pro — Agents That Act on Connected Data |
| Track 2 prize | PS5 with GTA VI — Agent Memory and Coordination |
| Track 3 prize | M6 Mac Mini — Company Brain |
| Side prize | AirPods 5 — best blog post (1 winner) |
| Side prize | T-shirt — every member of the top 50 teams |
| Support | FalkorDB Discord open the whole event (team finding + graph-model help) |

## The three tracks, decoded

**Track 1 — Agents That Act on Connected Data.** "Use the graph to decide **and act**." Key focus: multi-hop reasoning, graph queries and algorithms *as agent tools*, tool selection through MCP, actions based on what the graph shows, explainable results. Examples they gave: fraud investigation, security finding triage, codebase navigation.
→ Hidden requirement: the agent must take an *action* (open a ticket, page someone, roll back, quarantine, approve/deny), not just answer. And the action must be chosen by a graph result, with the path shown.

**Track 2 — Agent Memory and Coordination.** Key focus: episodic, semantic, procedural memory; persistent conversation history; shared state and handoffs between agents; high-concurrency reads/writes; separate memory per user/tenant.
→ Hidden requirement: you need to *demonstrate* concurrency and isolation, not just claim them. A load script and a leak test are cheap and rare.

**Track 3 — Company Brain.** Key focus: knowledge from docs/tickets/chats in one graph; who owns what and who knows what; tracing decisions to source; keeping knowledge current as things change; answers with clear sources.
→ Hidden requirement: "keeping knowledge current" = temporal modelling (superseded facts, valid-from/to). Most entries will ignore it.

## The rules that actually decide the winner

| # | Rule (paraphrased) | What it means for you |
|---|---|---|
| 2 | FalkorDB must be the *primary* graph DB and support a *central* part of the product | Not a side feature. Core path of the demo must hit it |
| 3 | **Graph must do real work. If the product still works with FalkorDB removed, graph is decoration → doesn't qualify** | The single most important rule. Build a "FalkorDB off" switch and show the product failing. Show A/B vs vector-only |
| 4 | Docker / self-host / FalkorDB Cloud all fine; any language/framework/deploy | Use whatever you're fastest in |
| 5 | Must **name every track** you enter at submission | Decide tracks in advance (recommend: all three, primary = the one with strongest demo) |
| 6 | Data must be public, synthetic, or your own. No private/login-protected/paywalled/personal data | Use synthetic company data (generated, seeded, reproducible). Optionally mix a public GitHub repo |
| 8 | Main coding/design must start after Oct 15 12:01 AM IST. Notes/sketches before are OK | Fine. Don't reuse an old repo as the core (see below) |
| 9 | Libraries, APIs, templates, public datasets allowed; **original work done during the hackathon is judged** | Use Graphiti/GraphRAG-SDK sparingly; your own graph logic must be visible |
| 10 | Submission must have: public repo; README with setup **and graph data model**; **the Cypher queries/algorithms the product depends on**; demo video; live deployment or full local instructions; the track(s) | Each is a checkbox a judge/automation will look for. Missing one is an avoidable loss |
| 11 | AI coding assistants allowed but **must be disclosed** | Add an "AI usage" section to README. Be specific |
| 12 | Participants must understand the code and explain graph model, queries, architecture, technical decisions | Be ready for Q&A. Doc 06 has prep |
| 13 | Entirely-AI-generated projects without meaningful participant contribution/verification/understanding may be rejected | Write the schema, the verifier and the eval yourself (or at least hand-review and be able to defend each) |
| 17 | Plagiarism / manipulating judging → disqualification | Don't clone Graphiti and rebrand. Cite everything |

## What the judges are probably scoring (inferred, not published)

Weighting is a guess. Order reflects what the rules and track text emphasise:

1. **Graph centrality** — is the graph the product? (rule 3, rule 2)
2. **Explainability / traceability** — the event tagline is "makes decisions you can trace"; every track lists explainable/source-backed answers
3. **Track fit** — does it hit the "key focus" bullets by name
4. **Demo clarity** — 3 minutes, working, not slideware
5. **Completeness** — repo, README, data model, queries, deploy
6. **Technical depth** — algorithms as tools, temporal edges, concurrency, tenant isolation, MCP
7. **Originality of the problem** — not "chat with your PDFs"

## Competitive reality

- ~7.6k registered; the dominant submissions will be: "GraphRAG over a PDF", "knowledge-graph chatbot", "repo explainer". These fail rule 3 in spirit because swapping FalkorDB for a vector store barely changes them.
- The winning edge is **evidence that the graph was necessary**: multi-hop questions that vector RAG gets wrong and the graph gets right, with the numbers on screen.
- Three separate track winners means **narrow track fit beats breadth** if you enter only one, but entering all three is free. A single project can be the best in one and merely credible in others; you only need one win.

## Traps

1. **Reusing an existing project** (FAQ asks "Can I continue an existing project?"). Rule 8 says main work must start after the start. Don't build on old code. Fresh repo, first commit timestamp after Oct 15.
2. **Decorative graph.** A force-directed visual on top of Postgres rows. Disqualifying by their own words.
3. **Undisclosed AI usage.** Disclose.
4. **Private data.** No real Slack exports, no real employee info.
5. **No deployment, no video.** Both are required. A project that runs only on your laptop with no video loses before judging starts.
6. **Time.** Late-night "one more feature" is how people miss 11:59 PM IST. Freeze features 6 hours before the deadline.
7. **Timezone.** 11:59 PM IST is 18:29 UTC, 2:29 PM US Eastern (Oct 18), 11:29 AM US Pacific. Submit 3+ hours early regardless.
