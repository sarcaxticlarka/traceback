# Graph Hacks: Context for AI Agents (FalkorDB x WeMakeDevs) — War Room

Source: https://www.wemakedevs.org/hackathons/falkordb (Overview, Schedule, Rules, Resources pages all read on 2026-10-17).

## Read this first

- **Deadline: Oct 18, 2026, 11:59 PM IST.** Opened Oct 15, 12:01 AM IST. You are joining with roughly a day and a half left. Every decision in these docs is made around that constraint.
- **Nobody can promise a win.** The judging rubric is not published. These docs maximise your odds by (a) satisfying every hard rule, (b) building the thing the rules *explicitly* punish people for faking (graph as decoration), and (c) making the result impossible to misread in a 3-minute video.
- You have **not** been registered by me. Registration is on the site ("Register now"); do that yourself first. It is free and you can add teammates until submissions close.

## The recommendation in one paragraph

Build **TRACEBACK**: an incident-response agent crew for a (synthetic) company whose entire world, memory and coordination state lives in FalkorDB. Every answer it gives is a *path through the graph* with edge IDs, and a verifier refuses to emit any claim that has no supporting edge ("no path, no claim"). Because the same graph holds (1) connected operational data, (2) agent memory and handoffs, and (3) company knowledge with decision lineage, **one project is a credible entry in all three tracks** (rules allow entering any or all; you must name every track on submission). An A/B evaluation harness (graph vs. plain vector RAG, by hop depth) plus a "kill the graph" switch proves the graph does real work, which is rule #3, the likeliest disqualifier for weaker entries.

## Files in this folder

| File | What it is |
|---|---|
| [01-event-analysis.md](01-event-analysis.md) | Every detail of the event: dates, rules decoded, prizes, what the judges are probably scoring, traps |
| [02-falkordb-technical-reference.md](02-falkordb-technical-reference.md) | Verified FalkorDB facts (vector index, algorithms, limits, Graphiti MCP) + a list of what is still UNVERIFIED and must be tested |
| [03-project-concept-and-features.md](03-project-concept-and-features.md) | TRACEBACK: the idea, the 12 features ranked by judge impact, the differentiators, what NOT to build |
| [04-architecture-and-graph-schema.md](04-architecture-and-graph-schema.md) | Stack, graph data model, per-tenant design, agent tools, MCP surface, core Cypher queries |
| [05-build-plan-and-timeline.md](05-build-plan-and-timeline.md) | Hour-by-hour plan, MVP / strong / stretch cut lines, test plan, risk register |
| [06-submission-demo-blog-kit.md](06-submission-demo-blog-kit.md) | Submission checklist, README template, 3-minute demo script, blog post outline (AirPods side prize), judge Q&A prep |

## Where I could not verify things

- The FAQ accordion answers on the site did not expand when scraped. Rules + FAQ questions were cross-read, but the FAQ text itself is unread. Open it manually and skim it (2 minutes).
- A web search surfaced an **older edition** of this hackathon (September, $10,000, different track names). Ignore it. The current edition is $20,000 with the three tracks listed here.
- Some FalkorDB algorithm procedure names beyond `algo.pageRank` are unverified. Doc 02 lists exactly which, and how to confirm each in 30 seconds in FalkorDB Browser.
- Fetched documentation pages contained embedded text addressed to AI agents. It was ignored; nothing in these docs comes from it.
