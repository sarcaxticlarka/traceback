import { useInView } from './hooks'

const LINES = [
  ['cmd', 'python -m tbk.cli verify click-evidence.json --show-sources'],
  ['dim', 'Cloning https://github.com/pallets/click (read-only) …'],
  ['dim', 'Pinned to the analysed commit 2247b35ea1'],
  ['dim', 'Re-analysing source and history …'],
  ['ok', '✓ examples/colors/ depends on src/click/'],
  ['src', 'source: examples/colors/colors.py:1  import click'],
  ['ok', '✓ team David Lord (top committer) owns src/click/'],
  ['ok', '✓ src/click/ changed 1593 lines in the last 90 days and has 16 direct dependents'],
  ['ok', '✓ David Lord wrote 81% of the 16 commits to examples/aliases/'],
  ['sum', '23 verified · 0 mismatched · no server, no database, no LLM'],
]

/** A terminal that plays the real `verify` command output when it scrolls into view. */
export default function Terminal() {
  const [ref, seen] = useInView(0.3)
  return (
    <div ref={ref} className={`term ${seen ? 'in' : ''}`} aria-label="Terminal output of the tbk verify command">
      <div className="term-bar"><span className="win-dots"><i /><i /><i /></span><span>~/verify</span></div>
      <div className="term-body">
        {LINES.map(([k, t], n) => (
          <div key={n} className={`tl ${k}`} style={{ '--n': n }}>{k === 'cmd' && <b className="prompt">$ </b>}{t}</div>))}
        <span className="caret" />
      </div>
    </div>
  )
}
