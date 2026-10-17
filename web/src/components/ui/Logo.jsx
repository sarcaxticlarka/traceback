/** Three nodes joined by a traced path: the product idea in one mark. */
export function LogoMark({ size = 26 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path d="M7 24 15 9l10 11" stroke="var(--line-2)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7 24 15 9" stroke="var(--accent)" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="7" cy="24" r="3.6" fill="var(--accent)" /><circle cx="15" cy="9" r="3.6" fill="var(--text)" /><circle cx="25" cy="20" r="3.6" fill="var(--surface-3)" stroke="var(--line-2)" />
    </svg>
  )
}
export default function Logo({ size = 26 }) {
  return <span className="logo"><LogoMark size={size} /><span className="logo-word">TRACEBACK</span></span>
}
