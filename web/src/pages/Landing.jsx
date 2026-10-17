import { useEffect, useState } from 'react'
import { api } from '../api'
import { go } from '../lib/router'
import Icon from '../components/ui/Icon'
import Logo from '../components/ui/Logo'
import Bento from './landing/Bento'
import CompareDemo from './landing/CompareDemo'
import ProductWindow from './landing/ProductWindow'
import Terminal from './landing/Terminal'
import { CountUp, Reveal, spot } from './landing/hooks'

const REPO = 'https://github.com/sarcaxticlarka/traceback'
const PLACEHOLDERS = ['https://github.com/pallets/click', 'https://github.com/expressjs/express', 'https://github.com/gin-gonic/gin', 'https://github.com/tiangolo/fastapi']
const FALLBACK_RUNS = [['pallets/click', 100, 25], ['psf/requests', 100, 0], ['expressjs/express', 100, 27], ['spf13/cobra', 100, 0], ['gin-gonic/gin', 100, 0], ['tiangolo/fastapi', 100, 10]]

// plain "#id" links would hit the hash router, so scroll instead
const scrollTo = (id) => (e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }

function Nav() {
  const [stuck, setStuck] = useState(false)
  useEffect(() => { const on = () => setStuck(window.scrollY > 12); on(); window.addEventListener('scroll', on, { passive: true }); return () => window.removeEventListener('scroll', on) }, [])
  return (
    <header className={`lp-nav ${stuck ? 'stuck' : ''}`}>
      <div className="wrap nav-in">
        <a href="#/" className="nav-logo" aria-label="TRACEBACK home"><Logo /></a>
        <nav aria-label="Primary">
          <a href="#how" onClick={scrollTo('how')}>How it works</a><a href="#product" onClick={scrollTo('product')}>Product</a>
          <a href="#proof" onClick={scrollTo('proof')}>Proof</a><a href="#verify" onClick={scrollTo('verify')}>Verify</a><a href="#/app/method">Method</a>
        </nav>
        <span className="sp" />
        <a className="nav-gh hide-sm" href={REPO} target="_blank" rel="noreferrer"><Icon name="github" size={15} /> GitHub</a>
        <button className="pill-btn ghost hide-sm" onClick={() => go('/app/investigate')}>Console</button>
        <button className="pill-btn" onClick={() => go('/app/lab')}>Analyze a repo</button>
      </div>
    </header>
  )
}

function Hero() {
  const [url, setUrl] = useState('')
  const [ph, setPh] = useState(0)
  useEffect(() => { const t = setInterval(() => setPh((p) => (p + 1) % PLACEHOLDERS.length), 2600); return () => clearInterval(t) }, [])
  const submit = (e) => { e.preventDefault(); go('/app/lab', url.trim() ? { repo: url.trim() } : undefined) }
  return (
    <section className="hero2">
      <div className="aurora" aria-hidden="true"><i className="a1" /><i className="a2" /><i className="a3" /><i className="a4" /></div>
      <div className="hero-grid" aria-hidden="true" />
      <div className="wrap hero-in">
        <a className="announce" href="#verify" onClick={scrollTo('verify')}><span className="new">New</span> Verify any claim on your own machine <Icon name="chevron" size={13} /></a>
        <h1 className="h-display">Answers you<br />can <span className="grad">trace<svg viewBox="0 0 300 22" aria-hidden="true"><path d="M3 15 C 60 3, 120 21, 190 9 S 280 6, 297 12" /></svg></span></h1>
        <p className="sub">AI agents that investigate incidents and codebases over a graph, and refuse to say anything they can't prove. Every claim carries the exact edges, files and commits behind it.</p>
        <form className="pillform" onSubmit={submit}>
          <Icon name="github" size={18} />
          <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder={PLACEHOLDERS[ph]} aria-label="GitHub repository URL" />
          <button type="submit" className="go">Analyze <Icon name="chevron" size={15} /></button>
        </form>
        <div className="micro">
          <span><Icon name="shield" size={13} /> Public repos, read-only</span><span><Icon name="eye" size={13} /> Your code is never executed</span>
          <span><Icon name="database" size={13} /> Keep the graph in your own FalkorDB</span>
        </div>
      </div>
      <div className="wrap win-wrap"><div className="win-glow" aria-hidden="true" /><ProductWindow /></div>
    </section>
  )
}

function Marquee({ runs }) {
  const items = [...runs, ...runs]
  return (
    <div className="marquee" aria-label="Benchmark results on real repositories">
      <div className="marq-track">
        {items.map(([name, g, d], i) => (
          <span key={i} className="marq-item"><Icon name="github" size={14} /> <b>{name}</b><span className="mono-label">graph <em className="g">{g}%</em> · docs <em>{d}%</em></span></span>))}
      </div>
    </div>
  )
}

const STEPS = [
  ['01', 'Ingest', 'Clone a public repo or unpack your zip. Parse imports, read git history, CODEOWNERS and docs.'],
  ['02', 'Build the graph', 'Modules, people, commits, owners and decisions become nodes and edges that remember why they exist.'],
  ['03', 'Walk it', '21 tools: blast radius, change impact, hotspots, bus factor, PageRank, decision lineage.'],
  ['04', 'Agents act', 'A planner (built-in, or any LLM with failover) picks tools. Agents hand work through graph state.'],
  ['05', 'Verify', 'Each claim is re-queried by edge id and entity-checked. Unsupported claims are withheld.'],
]

function Head({ kicker, children, sub }) {
  return <Reveal className="sec-head"><span className="mono-label k">{kicker}</span><h2 className="h-sec">{children}</h2>{sub && <p>{sub}</p>}</Reveal>
}

export default function Landing() {
  const [real, setReal] = useState([])
  const [ev, setEv] = useState(null)
  useEffect(() => { api.benchReal().then(setReal).catch(() => {}); api.evalResults().then(setEv).catch(() => {}) }, [])
  const ok = real.filter((r) => r.aggregate)
  const runs = ok.length ? ok.map((r) => [r.repo, Math.round(r.aggregate.all.graph_exact * 100), Math.round(r.aggregate.all.docs_exact * 100)]) : FALLBACK_RUNS
  const realQ = ok.reduce((n, r) => n + r.aggregate.all.n, 0) || 110
  const gAvg = ok.length ? Math.round((ok.reduce((n, r) => n + r.aggregate.all.graph_exact * r.aggregate.all.n, 0) / realQ) * 100) : 100
  const dAvg = ok.length ? Math.round((ok.reduce((n, r) => n + r.aggregate.all.docs_exact * r.aggregate.all.n, 0) / realQ) * 100) : 13
  const hop3 = ev?.aggregate?.['3+-hop'] ? Math.round(ev.aggregate['3+-hop'].docs_exact * 100) : 10

  return (
    <div className="lp">
      <div className="grain" aria-hidden="true" />
      <Nav />
      <Hero />
      <Marquee runs={runs} />

      <section className="section" id="how">
        <div className="wrap">
          <Head kicker="How it works" sub="Nothing here is a black box: ingestion and verification are deterministic code, and the graph is inspectable in the FalkorDB browser.">From a repository to a <em>verified</em> answer</Head>
          <div className="steps">
            {STEPS.map(([n, h, p], i) => (
              <Reveal key={n} delay={i * 70} className={`step-card glass ${i === 1 || i === 4 ? 'hot' : ''}`} onMouseMove={spot}>
                <span className="mono-label n">{n}</span><h3>{h}</h3><p>{p}</p></Reveal>))}
          </div>
        </div>
      </section>

      <section className="section" id="compare">
        <div className="wrap">
          <Head kicker="Why a graph" sub="Retrieval finds the pages that mention a module. A graph finds what depends on it, who owns it, and what changed, and can show its work.">Same question. <em>Very</em> different answers.</Head>
          <Reveal><CompareDemo /></Reveal>
        </div>
      </section>

      <section className="section" id="product">
        <div className="wrap">
          <Head kicker="Product" sub="One graph, one verifier, many ways in.">Everything an investigation needs</Head>
          <Bento />
        </div>
      </section>

      <section className="section" id="proof">
        <div className="wrap">
          <Head kicker="Proof" sub="Auto-generated questions about real repositories. Ground truth comes from the static analyser and raw commit list, never from the database under test.">Measured, <em>not</em> claimed</Head>
          <div className="numbers2">
            {[[realQ, '', 'questions across real public repositories'], [gAvg, '%', 'graph agent, exact match'], [dAvg, '%', 'documents-only baseline, same questions'], [hop3, '%', 'documents-only once an answer needs 3+ relationships']].map(([v, s, l], i) => (
              <Reveal key={l} delay={i * 80} className={`num2 glass ${i === 1 ? 'hl' : ''}`} onMouseMove={spot}>
                <div className="big"><CountUp to={v} suffix={s} /></div><p>{l}</p></Reveal>))}
          </div>
          <Reveal className="proof-cta"><span className="muted">100% of the graph agent's claims were re-verified against FalkorDB in both benchmarks.</span>
            <span className="row"><button className="pill-btn ghost" onClick={() => go('/app/proof')}>See the benchmarks</button><button className="pill-btn ghost" onClick={() => go('/app/method')}>Read the method</button></span></Reveal>
        </div>
      </section>

      <section className="section" id="verify">
        <div className="wrap verify-grid">
          <div>
            <Head kicker="Trust" sub="A system that says 'trust me' isn't proving anything. You can check TRACEBACK without trusting TRACEBACK.">Don't take our <em>word</em> for it</Head>
            <div className="trust-list">
              {[['terminal', 'Re-verify on your machine', 'Download an evidence bundle; one command re-derives every fact from the source. No server, no database, no LLM.'],
                ['database', 'Keep your data on your FalkorDB', 'Connect your own instance and the graph is written there, never to ours. Connection held per request, in memory.'],
                ['scale', 'Audit with your own key', 'Your model gets each claim and its evidence and gives an independent second opinion.']].map(([ic, h, p], i) => (
                <Reveal key={h} delay={i * 90} className="trust-item"><span className="ti-ic"><Icon name={ic} size={18} /></span><div><h3>{h}</h3><p>{p}</p></div></Reveal>))}
            </div>
          </div>
          <Reveal delay={120}><Terminal /></Reveal>
        </div>
      </section>

      <section className="section" id="ai">
        <div className="wrap">
          <Head kicker="Transparency" sub="It works with no model at all. With your key, the model gets three narrow jobs and none can change what is true.">What the AI does, and what it <em>doesn't</em></Head>
          <div className="ai-grid">
            <Reveal className="glass ai-card" onMouseMove={spot}><h3><Icon name="chip" size={16} /> Deterministic code, always</h3>
              <ul><li><b>Parsing and ingest.</b> Static analysis; no repo code is executed.</li><li><b>Graph and queries.</b> Every tool is Cypher or a FalkorDB algorithm.</li>
                <li><b>Ranking.</b> Suspects, hotspots, runbooks, risk: plain formulas.</li><li><b>Verification.</b> Edges, validity, properties, entity grounding.</li></ul></Reveal>
            <Reveal delay={90} className="glass ai-card" onMouseMove={spot}><h3><Icon name="key" size={16} /> Optional LLM, your keys</h3>
              <ul><li><b>Choose tools</b> instead of the built-in playbook.</li><li><b>Answer free-form questions</b> by calling the same tools.</li>
                <li><b>Polish wording.</b> The verifier rejects any added entity.</li><li><b>Never</b> invents facts or sees your source files.</li></ul></Reveal>
          </div>
        </div>
      </section>

      <section className="cta2">
        <div className="aurora soft" aria-hidden="true"><i className="a1" /><i className="a2" /><i className="a3" /></div>
        <div className="wrap center">
          <Reveal><h2 className="h-display sm">Ask your codebase <span className="grad">why.</span></h2>
            <p className="sub">Paste a repository and get hotspots, bus-factor risks, a dependency map and verified change impact in under a minute.</p>
            <div className="row" style={{ justifyContent: 'center' }}>
              <button className="pill-btn big" onClick={() => go('/app/lab')}>Analyze a repository <Icon name="chevron" size={16} /></button>
              <button className="pill-btn ghost big" onClick={() => go('/app/investigate')}>Watch an investigation</button>
            </div></Reveal>
        </div>
      </section>

      <footer className="lp-foot2">
        <div className="wrap foot-grid">
          <div><Logo size={22} /><p className="muted" style={{ maxWidth: 320, marginTop: 12 }}>Graph-backed agents that can't say anything they can't trace. Open source, built on FalkorDB.</p></div>
          <div><span className="mono-label">Product</span><a href="#/app/lab">Analyze your code</a><a href="#/app/investigate">Investigate</a><a href="#/app/ask">Company brain</a><a href="#/app/memory">Agent memory</a></div>
          <div><span className="mono-label">Trust</span><a href="#/app/proof">Benchmarks</a><a href="#/app/method">Method</a><a href="#verify" onClick={scrollTo('verify')}>Verify locally</a></div>
          <div><span className="mono-label">Build</span><a href={REPO} target="_blank" rel="noreferrer">GitHub</a><a href={`${REPO}/blob/main/docs/REAL_WORLD.md`} target="_blank" rel="noreferrer">Real-world guide</a><a href={`${REPO}/blob/main/docs/API.md`} target="_blank" rel="noreferrer">API &amp; MCP</a></div>
        </div>
        <div className="wrap foot-base"><span>Repository analyses are deleted after 12 hours. A synthetic demo company is included.</span><span className="mono-label">Built with FalkorDB</span></div>
      </footer>
    </div>
  )
}
