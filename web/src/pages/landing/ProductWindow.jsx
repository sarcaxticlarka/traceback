import Icon from '../../components/ui/Icon'

const NODES = [
  [70, 150, '#f472b6', 'alert', 0], [190, 80, '#7ba7ff', 'checkout-api', 0], [300, 160, '#7ba7ff', 'payments-api', 1], [430, 90, '#7ba7ff', 'ledger-store', 2],
  [440, 220, '#ff7a6b', 'deploy b93ac82', 3], [320, 255, '#f5c451', 'Mia Evans', 4], [190, 235, '#b79cff', 'team payments', 5],
]
const BASE = ['M80 146 L180 86', 'M200 86 L292 154', 'M310 156 L420 94', 'M432 106 L438 208', 'M330 250 L428 226', 'M204 230 L420 100']
const HOT = BASE.slice(0, 5)

/** The hero's product: a miniature of the real console tracing a claim to its evidence, on a loop. */
export default function ProductWindow() {
  return (
    <div className="win" aria-label="Animated preview of an investigation in the TRACEBACK console">
      <div className="win-bar">
        <span className="win-dots"><i /><i /><i /></span>
        <span className="win-url">traceback / investigate / <b>alert:LIVE-1</b></span>
        <span className="win-live"><i /> 27 claims verified</span>
      </div>
      <div className="win-body">
        <aside className="win-side">
          {[['search', 'Investigate', true], ['message', 'Company brain'], ['database', 'Agent memory'], ['github', 'Analyze code'], ['chart', 'Proof']].map(([ic, l, on]) => (
            <span key={l} className={on ? 'on' : ''}><Icon name={ic} size={14} />{l}</span>))}
        </aside>
        <div className="win-main">
          <div className="win-head">
            <p>Likely cause: <b>deploy b93ac82</b> to ledger-store by Mia Evans, <b>2 dependency hops</b> from the alert. Owner: team payments. Blast radius: 7 services.</p>
            <div className="win-chips"><span className="wchip ok"><Icon name="shield" size={11} /> Grounded 100%</span><span className="wchip">offline-playbook</span><span className="wchip">1.4 s</span></div>
          </div>
          <div className="win-cols">
            <svg className="win-graph" viewBox="0 0 520 300" role="img" aria-hidden="true">
              {BASE.map((d) => <path key={d} className="w-edge" d={d} />)}
              {HOT.map((d, i) => <path key={d} className="w-hot" style={{ '--i': i }} d={d} />)}
              {NODES.map(([x, y, c, t, i]) => (
                <g key={t} transform={`translate(${x},${y})`}>
                  <circle className="w-halo" style={{ '--i': i, fill: c }} r="16" />
                  <circle className="w-node" style={{ fill: c }} r="9" />
                  <text y="26" textAnchor="middle">{t}</text>
                </g>))}
            </svg>
            <div className="win-claims">
              <div className="wc" style={{ '--i': 3 }}><Icon name="check" size={13} /><span>payments-api depends on ledger-store</span><code>2 edges</code></div>
              <div className="wc" style={{ '--i': 4.2 }}><Icon name="check" size={13} /><span>Mia Evans authored deploy b93ac82 to ledger-store</span><code>2 edges</code></div>
              <div className="wc" style={{ '--i': 5.4 }}><Icon name="check" size={13} /><span>team payments owns ledger-store</span><code>1 edge</code></div>
              <div className="wc bad" style={{ '--i': 6.6 }}><Icon name="x" size={13} /><span>ledger-store is owned by team trust</span><code>withheld · no path</code></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
