import Icon from '../../components/ui/Icon'
import { Reveal, spot } from './hooks'

const Tile = ({ cls, icon, title, children, visual, delay }) => (
  <Reveal className={`bento-tile glass ${cls}`} delay={delay} onMouseMove={spot}>
    <div className="bt-text"><span className="bt-ic"><Icon name={icon} size={16} /></span><h3>{title}</h3><p>{children}</p></div>
    <div className="bt-visual" aria-hidden="true">{visual}</div>
  </Reveal>
)

const ProofVis = () => (
  <div className="bv-claims">
    {[['ok', 'src/api/ depends on lib/core/', 'src/api/routes.py:12'], ['ok', 'Ana Ruiz authored deploy 7f3a91c', '2 edges'], ['bad', 'billing-api is also affected', 'withheld: not in evidence']].map(([k, t, m], i) => (
      <div key={t} className={`bv-claim ${k}`} style={{ '--i': i }}><Icon name={k === 'ok' ? 'check' : 'x'} size={13} /><span>{t}</span><code>{m}</code></div>))}
  </div>
)
const ImpactVis = () => (
  <div className="bv-impact">
    <div className="bv-ring"><b>64</b><small>risk</small></div>
    <div className="bv-people"><span>AR</span><span>LP</span><span>SO</span><em>11 modules depend on this</em></div>
  </div>
)
const MapVis = () => (
  <svg viewBox="0 0 240 150" className="bv-map">
    {[[120, 75, 30, 40], [120, 75, 200, 30], [120, 75, 210, 105], [120, 75, 40, 110], [120, 75, 120, 135], [30, 40, 20, 80], [200, 30, 225, 60]].map(([a, b, c, d], i) => <line key={i} x1={a} y1={b} x2={c} y2={d} />)}
    {[[30, 40, 5], [200, 30, 6], [210, 105, 5], [40, 110, 6], [120, 135, 4], [20, 80, 3], [225, 60, 3]].map(([x, y, r], i) => <circle key={i} cx={x} cy={y} r={r} className="n" />)}
    <circle cx="120" cy="75" r="15" className="hub" /><circle cx="120" cy="75" r="15" className="pulse" />
  </svg>
)
const FailVis = () => (
  <div className="bv-fail">
    <div className="fp a"><i /> Anthropic <em>429 rate limit</em></div>
    <div className="fp b"><i /> OpenAI <em>answered</em></div>
    <div className="fp c"><i /> Groq <em>standby</em></div>
  </div>
)
const MemVis = () => (
  <svg viewBox="0 0 220 90" className="bv-mem">
    <path className="area" d="M0 76 C30 70 40 54 70 48 S120 28 150 22 S200 14 220 12 L220 90 L0 90Z" />
    <path className="line" d="M0 76 C30 70 40 54 70 48 S120 28 150 22 S200 14 220 12" />
    <text x="4" y="14">runbook choice: 70% → 86%</text>
  </svg>
)
const CliVis = () => (
  <div className="bv-cli">
    <div><b>$</b> python -m tbk.cli impact . --base main</div>
    <div className="o">### TRACEBACK impact: risk 64/100</div>
    <div className="o">Touches `src/api/` · 11 modules depend on this</div>
    <div className="o">Suggested reviewers: Ana Ruiz, Lee Park</div>
    <div className="o ok">23 verified claims · 100% grounded</div>
  </div>
)

export default function Bento() {
  return (
    <div className="bento">
      <Tile cls="t-proof" icon="shield" title="Proof-carrying answers" delay={0} visual={<ProofVis />}>
        Every claim cites graph edges, import lines or commits. A verifier re-queries the database and <b>withholds</b> anything it can't confirm, including names a model slips in.</Tile>
      <Tile cls="t-impact" icon="git" title="Change impact, with reviewers" delay={80} visual={<ImpactVis />}>
        Pick a commit: what depends on it, who owns it, who should review it, and which risks apply.</Tile>
      <Tile cls="t-map" icon="route" title="Real dependency graphs" delay={0} visual={<MapVis />}>
        Imports resolved in Python, JS/TS, Go, Java, C/C++. Cycle-safe traversal stays fast on big repos.</Tile>
      <Tile cls="t-fail" icon="key" title="Any model, your keys" delay={80} visual={<FailVis />}>
        Anthropic or any OpenAI-compatible API. One hits a limit? The next takes over mid-investigation.</Tile>
      <Tile cls="t-mem" icon="database" title="Memory that learns" delay={160} visual={<MemVis />}>
        Episodes, facts that supersede each other, and runbook stats that improve with every outcome.</Tile>
      <Tile cls="t-cli" icon="terminal" title="In CI, in your editor" delay={0} visual={<CliVis />}>
        A verified comment on every pull request, and 21 tools over MCP for Claude Desktop, Cursor or your own agent.</Tile>
    </div>
  )
}
