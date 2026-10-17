import { useEffect, useState } from 'react'
import { api } from '../api'
import { go } from '../lib/router'
import Icon from '../components/ui/Icon'
import Logo from '../components/ui/Logo'
import { GroupedBars } from '../components/Common'

function HeroTrace() {
  return (
    <div className="trace-card" aria-label="Animated example of a claim being traced to graph edges">
      <div className="bar-top"><span className="dots"><i /><i /><i /></span><span className="mono">investigate · alert:LIVE-1</span></div>
      <svg className="trace-svg" viewBox="0 0 520 250" role="img" aria-hidden="true">
        {/* base graph */}
        <g className="tr-edge-group">
          <path className="tr-edge" d="M62 62 L186 62" /><path className="tr-edge" d="M196 66 L322 112" />
          <path className="tr-edge" d="M338 108 L430 66" /><path className="tr-edge" d="M440 82 L440 160" />
          <path className="tr-edge" d="M334 196 L426 176" /><path className="tr-edge" d="M214 178 L424 74" />
        </g>
        {/* traced path */}
        <path className="tr-hot" style={{ '--i': 0 }} d="M62 62 L186 62" />
        <path className="tr-hot" style={{ '--i': 1 }} d="M196 66 L322 112" />
        <path className="tr-hot" style={{ '--i': 2 }} d="M338 108 L430 66" />
        <path className="tr-hot" style={{ '--i': 3 }} d="M440 82 L440 160" />
        <path className="tr-hot" style={{ '--i': 4 }} d="M334 196 L426 176" />
        {[[50, 62, '#f472b6', 'alert', 0], [190, 62, '#7ba7ff', 'checkout-api', 0], [330, 112, '#7ba7ff', 'payments-api', 1], [440, 66, '#7ba7ff', 'ledger-store', 2],
          [440, 172, '#ff7a6b', 'deploy b93ac82', 3], [324, 200, '#f5c451', 'Mia Evans', 4], [204, 182, '#b79cff', 'team payments', 5]].map(([x, y, c, t, i]) => (
          <g key={t} className="tr-node" transform={`translate(${x},${y})`}>
            <circle className="tr-pulse" style={{ '--i': i, fill: c, stroke: 'var(--surface)', strokeWidth: 3 }} r="10" />
            <text x="0" y="26" textAnchor="middle">{t}</text>
          </g>
        ))}
      </svg>
      <div className="tr-claims">
        <div className="tr-claim" style={{ '--i': 3 }}><span className="ok"><Icon name="check" size={15} /></span>payments-api depends on ledger-store<code>edges 4101 · 4388</code></div>
        <div className="tr-claim" style={{ '--i': 4.4 }}><span className="ok"><Icon name="check" size={15} /></span>Mia Evans authored deploy b93ac82 to ledger-store<code>edges 6120 · 6119</code></div>
        <div className="tr-claim bad" style={{ '--i': 5.8 }}><span className="ok"><Icon name="x" size={15} /></span>ledger-store is owned by team trust<code>withheld · no path</code></div>
      </div>
    </div>
  )
}

const FEATURES = [
  ['shield', 'Proof-carrying answers', 'Every statement cites graph edge ids. A verifier re-queries the database and withholds anything it cannot confirm, including names a model tries to slip in.'],
  ['git', 'Change impact and reviewers', 'Paste a commit or a PR: see which modules depend on it, who owns them, who knows them best, and which risks (churn, single-author code) apply.'],
  ['route', 'Cycle-safe graph reasoning', 'Blast radius, dependency paths, PageRank and betweenness on real import graphs with cycles. Level-by-level traversal keeps queries fast on large repos.'],
  ['database', 'Memory that updates', 'Episodes, facts with validity windows that supersede each other, and runbook statistics that improve with every outcome. All stored in the graph.'],
  ['users', 'Agents that hand off', 'Triage, Investigator and Remediator coordinate only through Task and Finding nodes. Atomic claims: 100 workers racing for one task produce one winner.'],
  ['plug', 'Any model, your keys', 'Anthropic, OpenAI, Gemini, Groq, OpenRouter and more. Add several keys; when one hits a rate limit the next takes over mid-investigation.'],
]

export default function Landing({ theme }) {
  const [url, setUrl] = useState('')
  const [ev, setEv] = useState(null)
  const [real, setReal] = useState([])
  useEffect(() => { api.evalResults().then(setEv).catch(() => {}); api.benchReal().then(setReal).catch(() => {}) }, [])

  const realQ = real.reduce((n, r) => n + (r.aggregate?.all?.n || 0), 0)
  const realG = real.reduce((n, r) => n + (r.aggregate?.all?.graph_exact || 0) * (r.aggregate?.all?.n || 0), 0)
  const realD = real.reduce((n, r) => n + (r.aggregate?.all?.docs_exact || 0) * (r.aggregate?.all?.n || 0), 0)
  const order = ['1-hop', '2-hop', 'temporal', '3+-hop']
  const groups = ev ? order.filter((b) => ev.aggregate[b]).map((b) => ({ label: b, a: ev.aggregate[b].graph_exact, b: ev.aggregate[b].docs_exact })) : []

  const submit = (e) => { e.preventDefault(); go('/app/lab', url.trim() ? { repo: url.trim() } : undefined) }

  return (
    <div className="lp">
      <header className="lp-nav">
        <div className="lp-wrap">
          <a href="#/" className="logo-link" style={{ textDecoration: 'none' }}><Logo /></a>
          <nav><a href="#how">How it works</a><a href="#proof">Proof</a><a href="#use">Use it</a><a href="#ai">The AI</a><a href="#/app/method">Method</a></nav>
          <span className="spacer" />
          <button className="btn quiet icon" onClick={theme.toggle} title="Toggle theme"><Icon name={theme.dark ? 'sun' : 'moon'} /></button>
          <button className="btn ghost sm hide-sm" onClick={() => go('/app/investigate')}>Open console</button>
          <button className="btn sm" onClick={() => go('/app/lab')}>Analyze a repo</button>
        </div>
      </header>

      <section className="hero">
        <div className="lp-wrap hero-grid">
          <div>
            <span className="eyebrow"><i /> Open source · built on FalkorDB</span>
            <h1 className="display">Answers you can <em>trace.</em></h1>
            <p className="lede">TRACEBACK investigates incidents and codebases with AI agents over a graph, and refuses to say anything it can't prove.
              Every claim carries the exact edges, files and commits behind it, re-checked against the database before you see it.</p>
            <form className="hero-form" onSubmit={submit}>
              <input type="url" placeholder="https://github.com/owner/repo" value={url} onChange={(e) => setUrl(e.target.value)} aria-label="GitHub repository URL" />
              <button className="btn lg" type="submit">Analyze <Icon name="chevron" size={16} /></button>
            </form>
            <div className="hero-note">
              <span><Icon name="shield" size={14} /> Public repos only, read-only</span>
              <span><Icon name="eye" size={14} /> Your code is never executed</span>
              <span><Icon name="clock" size={14} /> Deleted after 12 hours</span>
            </div>
            <div className="row" style={{ marginTop: 18 }}>
              <button className="btn ghost" onClick={() => go('/app/investigate')}><Icon name="play" size={14} /> Watch an incident investigation</button>
              <button className="btn quiet" onClick={() => go('/app/ask')}>Ask the company brain</button>
            </div>
          </div>
          <HeroTrace />
        </div>
        <div className="lp-wrap logos"><b>Built with</b><span>FalkorDB</span><span>Cypher</span><span>MCP</span><span>FastAPI</span><span>React</span><span>OpenAI-compatible APIs</span><span>Anthropic</span></div>
      </section>

      <section className="section" id="problem">
        <div className="lp-wrap">
          <div className="sec-head"><span className="kicker">The problem</span><h2>Agents see pieces, not the whole picture</h2>
            <p>Ask a chatbot "who should review this change?" and it will answer, confidently, from whatever text it retrieved. It can't follow the imports, doesn't know the owner changed in March, and can't show its work.</p></div>
          <div className="compare">
            <div className="col"><h3><Icon name="file" size={18} /> Documents + embeddings</h3>
              <ul><li><Icon name="x" size={16} style={{ color: 'var(--bad)' }} />Finds the chunks that <i>mention</i> a module, not the ones that depend on it</li>
                <li><Icon name="x" size={16} style={{ color: 'var(--bad)' }} />Cannot compose relationships across 2, 3, 4 hops</li>
                <li><Icon name="x" size={16} style={{ color: 'var(--bad)' }} />Stale READMEs beat the current owner</li>
                <li><Icon name="x" size={16} style={{ color: 'var(--bad)' }} />No way to check an answer</li></ul></div>
            <div className="col good"><h3><Icon name="route" size={18} /> A graph the agent can walk</h3>
              <ul><li><Icon name="check" size={16} style={{ color: 'var(--ok)' }} />Imports, ownership, authorship and decisions are edges, with validity windows</li>
                <li><Icon name="check" size={16} style={{ color: 'var(--ok)' }} />Blast radius, shortest paths, PageRank run inside the database</li>
                <li><Icon name="check" size={16} style={{ color: 'var(--ok)' }} />Time-travel: "who owned this on June 12th?"</li>
                <li><Icon name="check" size={16} style={{ color: 'var(--ok)' }} />Each claim lists its evidence and is re-verified</li></ul></div>
          </div>
        </div>
      </section>

      <section className="section tint" id="how">
        <div className="lp-wrap">
          <div className="sec-head"><span className="kicker">How it works</span><h2>From a repository to a verified answer</h2>
            <p>Nothing here is a black box: ingestion and verification are deterministic code, and the graph is inspectable in the FalkorDB browser.</p></div>
          <div className="flow">
            {[['01', 'Ingest', 'Clone a public repo (or unpack your zip), parse imports in Python, JS/TS, Go, Java/Kotlin, C/C++, read git history and CODEOWNERS.'],
              ['02', 'Build the graph', 'Modules, people, commits, owners, docs and decisions become nodes and edges, each recording why it exists.', true],
              ['03', 'Tools', '21 Cypher and algorithm tools: blast radius, change impact, hotspots, bus factor, decision lineage, similar incidents.'],
              ['04', 'Agents', 'A planner picks tools (deterministic playbook, or any LLM with failover). Agents coordinate through graph state.'],
              ['05', 'Verify', 'Every claim is re-queried by edge id and entity-checked. Unsupported claims are withheld, not softened.']].map(([n, h, p, hot]) => (
              <div key={n} className={`st ${hot ? 'hot' : ''}`}><span className="n">{n}</span><h4>{h}</h4><p>{p}</p></div>))}
          </div>
        </div>
      </section>

      <section className="section" id="features">
        <div className="lp-wrap">
          <div className="sec-head"><span className="kicker">Capabilities</span><h2>Built for people who have to be right</h2></div>
          <div className="grid3">{FEATURES.map(([ic, h, p]) => <div className="feat" key={h}><div className="ic"><Icon name={ic} size={19} /></div><h3>{h}</h3><p>{p}</p></div>)}</div>
        </div>
      </section>

      <section className="section tint" id="proof">
        <div className="lp-wrap">
          <div className="sec-head"><span className="kicker">Proof</span><h2>Measured, not claimed</h2>
            <p>The same questions are put to the graph agent and to a documents-only baseline (hybrid retrieval plus a reader) over the same material. Ground truth comes from the static analyser and raw commit list, never from the database under test.</p></div>
          <div className="numbers">
            <div className="num"><div className="big acc">{realQ ? Math.round((realG / realQ) * 100) + '%' : '—'}</div><p>graph agent exact-match on {realQ || '…'} questions over {real.length || '…'} real public repositories</p></div>
            <div className="num"><div className="big">{realQ ? Math.round((realD / realQ) * 100) + '%' : '—'}</div><p>documents-only baseline on the same questions</p></div>
            <div className="num"><div className="big acc">100%</div><p>of the graph agent's claims re-verified against FalkorDB in both benchmarks</p></div>
            <div className="num"><div className="big">{ev ? ev.aggregate['3+-hop'] && Math.round(ev.aggregate['3+-hop'].docs_exact * 100) + '%' : '—'}</div><p>what documents-only manages once an answer needs 3+ relationships (graph: 100%)</p></div>
          </div>
          <div className="grid2e">
            <div className="card"><h3>Accuracy by relationships needed (demo company, 96 questions)</h3>{groups.length ? <GroupedBars groups={groups} aName="Graph agent" bName="Docs-only" /> : <div className="empty">Loading…</div>}</div>
            <div className="card"><h3>Real repositories (reproducible: <code>scripts/bench_real_repos.py</code>)</h3>
              <table><thead><tr><th>Repo</th><th className="num">Modules</th><th className="num">Commits</th><th className="num">Graph</th><th className="num">Docs</th></tr></thead>
                <tbody>{real.filter((r) => r.aggregate).map((r) => (
                  <tr key={r.repo}><td><a href={`https://github.com/${r.repo}`} target="_blank" rel="noreferrer">{r.repo}</a></td><td className="num">{r.stats.modules}</td><td className="num">{r.stats.commits}</td>
                    <td className="num">{Math.round(r.aggregate.all.graph_exact * 100)}%</td><td className="num">{Math.round(r.aggregate.all.docs_exact * 100)}%</td></tr>))}</tbody></table>
              <p className="muted" style={{ fontSize: 12.5, marginTop: 10 }}>The baseline sees 8 retrieved file chunks per question. A long-context model reading the whole repo would do better on small repos; the point is that relationships must be computed somewhere, and here the computation is checkable.</p></div>
          </div>
        </div>
      </section>

      <section className="section" id="use">
        <div className="lp-wrap">
          <div className="sec-head"><span className="kicker">Use it on real data</span><h2>Bring a repo, a folder, or your production catalogue</h2></div>
          <div className="input-modes">
            <div className="feat"><div className="ic"><Icon name="github" size={19} /></div><h3>Paste a GitHub URL</h3><p>Public repositories are cloned shallowly (read-only, no submodules, no hooks) and analysed in seconds. History gives owners, experts and churn.</p></div>
            <div className="feat"><div className="ic"><Icon name="folder" size={19} /></div><h3>Upload a folder or zip</h3><p>Pick a folder in your browser: source files are zipped locally and analysed. <code>.git</code> is never extracted from uploads, so structure and docs only.</p></div>
            <div className="feat"><div className="ic"><Icon name="database" size={19} /></div><h3>Upload production data</h3><p>Export services, dependencies, owners, deploys and alerts from Backstage, your deploy tool or PagerDuty as one JSON bundle. Same agents, same verifier.</p></div>
          </div>
          <div className="grid2e" style={{ marginTop: 14 }}>
            <div className="card"><h3>In CI: a verified PR comment</h3>
              <pre className="code">{`python -m tbk.cli impact . --base origin/main --head HEAD\n\n### TRACEBACK impact: risk 64/100\nTouches \`src/api/\` · 11 modules depend on this\nSuggested reviewers: Ana Ruiz, Lee Park\n⚠ src/api/ is a high-churn module (1718 lines / 90d)\nEvidence: 23 verified claims, 100% grounded`}</pre></div>
            <div className="card"><h3>Anywhere MCP works</h3>
              <pre className="code">{`{ "mcpServers": { "traceback": {\n  "command": ".venv/bin/python",\n  "args": ["-m", "tbk.mcp_server"] } } }`}</pre>
              <p className="muted" style={{ marginTop: 10, fontSize: 13 }}>Claude Desktop, Cursor or your own agent gets the same tools, and every response includes its verification block.</p></div>
          </div>
        </div>
      </section>

      <section className="section tint" id="ai">
        <div className="lp-wrap">
          <div className="sec-head"><span className="kicker">Transparency</span><h2>What the AI does, and what it doesn't</h2>
            <p>The system works with no model at all. When you add an API key, the model gets three narrow jobs and none of them can change what is true.</p></div>
          <div className="grid2e">
            <div className="card"><h3>Deterministic code (always)</h3>
              <table className="ai-table"><tbody>
                <tr><td>Parsing and ingest</td><td className="muted">Static analysis of imports, git log, CODEOWNERS. No repo code is executed.</td></tr>
                <tr><td>Graph and queries</td><td className="muted">Every fact is a node/edge; every tool is a Cypher query or FalkorDB algorithm.</td></tr>
                <tr><td>Ranking</td><td className="muted">Suspect scoring, hotspots, runbook success rates, risk: plain formulas.</td></tr>
                <tr><td>Verification</td><td className="muted">Edge existence, validity window, property checks, entity grounding.</td></tr>
                <tr><td>Benchmarks</td><td className="muted">Ground truth from the analyser's own model, not the database under test.</td></tr></tbody></table></div>
            <div className="card"><h3>Optional LLM (your keys, with failover)</h3>
              <table className="ai-table"><tbody>
                <tr><td>Choose tools</td><td className="muted">Decides which graph tool to call next, instead of the built-in playbook.</td></tr>
                <tr><td>Free-form questions</td><td className="muted">Calls the same tools to answer questions the rule parser does not recognise.</td></tr>
                <tr><td>Polish wording</td><td className="muted">Rewrites claim text; the verifier then rejects any added entity.</td></tr>
                <tr><td>Never</td><td className="muted">Invents facts, edits your code, or sees your source files: it receives tool results (module names, authors, commit subjects, short doc snippets).</td></tr></tbody></table></div>
          </div>
        </div>
      </section>

      <section className="cta-band section">
        <div className="lp-wrap">
          <h2 className="display">Ask your codebase <em>why.</em></h2>
          <p className="lede" style={{ margin: '0 auto 26px' }}>Paste a repository and get hotspots, bus-factor risks, a dependency map and verified change impact in under a minute.</p>
          <div className="row" style={{ justifyContent: 'center' }}>
            <button className="btn lg" onClick={() => go('/app/lab')}>Analyze a repository</button>
            <button className="btn ghost lg" onClick={() => go('/app/method')}>Read the method</button>
          </div>
        </div>
      </section>

      <footer className="lp-foot"><div className="lp-wrap">
        <Logo size={20} />
        <span>Open source. Data from public repositories is deleted after 12 hours. Synthetic demo company included.</span>
        <span className="row"><a href="#/app/method">Method</a><a href="#/app/proof">Benchmarks</a><a href="#/app/lab">Analyze</a></span>
      </div></footer>
    </div>
  )
}
