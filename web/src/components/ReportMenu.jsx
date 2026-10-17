import { useEffect, useRef, useState } from 'react'
import Icon from './ui/Icon'
import { Spinner } from './Common'
import { download, printHtml, slug } from '../lib/report'

/** Report button with a small menu. `build()` returns {html, md, name}; it may fetch data, so it is only called on click. */
export default function ReportMenu({ build, label = 'Report', size = 'sm' }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const off = (e) => { if (!ref.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', off)
    return () => document.removeEventListener('mousedown', off)
  }, [open])
  const act = async (kind) => {
    setBusy(true)
    try {
      const { html, md, name } = await build()
      if (kind === 'html') download(`${slug(name)}.html`, html, 'text/html')
      if (kind === 'md') download(`${slug(name)}.md`, md, 'text/markdown')
      if (kind === 'print') printHtml(html)
      setOpen(false)
    } finally { setBusy(false) }
  }
  return (
    <span className="menu-wrap" ref={ref}>
      <button className={`btn ghost ${size}`} onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open}>
        {busy ? <Spinner /> : <Icon name="report" size={14} />} {label}
      </button>
      {open && (
        <div className="menu" role="menu">
          <button role="menuitem" onClick={() => act('html')}><Icon name="download" size={14} /> Download report (HTML)</button>
          <button role="menuitem" onClick={() => act('print')}><Icon name="printer" size={14} /> Print / Save as PDF</button>
          <button role="menuitem" onClick={() => act('md')}><Icon name="file" size={14} /> Download Markdown</button>
        </div>
      )}
    </span>
  )
}
