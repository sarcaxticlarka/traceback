import { useState } from 'react'
import { api } from '../api'
import Icon from './ui/Icon'
import { Pill, Spinner } from './Common'

export const DB_KEY = 'traceback.byo.v1'
export const emptyDb = { host: '', port: 6379, password: '', ssl: true, enabled: false, remember: false }

export function loadDb() {
  try { const r = JSON.parse(localStorage.getItem(DB_KEY) || 'null'); if (r?.remember) return { ...emptyDb, ...r } } catch { /* ignore */ }
  return { ...emptyDb }
}
export function saveDb(d) {
  try { d.remember ? localStorage.setItem(DB_KEY, JSON.stringify(d)) : localStorage.removeItem(DB_KEY) } catch { /* ignore */ }
}

/** Where the graph of new analyses is stored: our shared server (default) or the user's own FalkorDB. */
export default function DbSettings({ open, onClose, db, setDb, privateAllowed }) {
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  if (!open) return null
  const up = (patch) => { const v = { ...db, ...patch }; setDb(v); saveDb(v); setRes(null) }
  const test = async () => { setBusy(true); setRes(null); try { setRes(await api.dbTest(db)) } catch (e) { setRes({ ok: false, error: String(e.message || e).replace(/^\d+\s*/, '').replace(/^\{"detail":"?|"?\}$/g, '') }) } setBusy(false) }
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal card" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Your FalkorDB">
        <div className="row between"><h3 style={{ margin: 0 }}>Where your data lives · your own FalkorDB</h3><button className="btn ghost" onClick={onClose}>Close</button></div>
        <p className="muted" style={{ marginTop: 10 }}>
          By default analyses are stored in the shared demo database for 12 hours. Connect a FalkorDB you run (FalkorDB Cloud, a VM, your network)
          and new analyses are written <b>there instead</b>: the graph (module names, edges, commit subjects, doc text) never touches our database, and
          the server keeps no copy. We hold your password in memory for each request only; it is never stored or logged here.
        </p>
        <div className="llm-row" style={{ gridTemplateColumns: '1.6fr .6fr 1.2fr auto' }}>
          <input type="text" placeholder="host, e.g. my-instance.falkordb.cloud" value={db.host} onChange={(e) => up({ host: e.target.value.trim() })} />
          <input type="text" placeholder="port" value={db.port} onChange={(e) => up({ port: e.target.value.replace(/\D/g, '') })} />
          <input type="password" autoComplete="off" placeholder="password (if any)" value={db.password} onChange={(e) => up({ password: e.target.value })} />
          <label className="check-row" style={{ alignItems: 'center' }}><input type="checkbox" checked={db.ssl} onChange={(e) => up({ ssl: e.target.checked })} />TLS</label>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn" disabled={busy || !db.host} onClick={test}>{busy ? <Spinner /> : <Icon name="database" size={15} />} Test connection</button>
          {res && (res.ok ? <Pill kind="ok">connected · {res.graphs} graph{res.graphs === 1 ? '' : 's'} · {res.latency_ms} ms{res.tls ? ' · TLS' : ''}</Pill>
            : <Pill kind="bad" title={res.error}>{res.kind || 'failed'}: {String(res.error).slice(0, 90)}</Pill>)}
        </div>
        <label className="check-row" style={{ marginTop: 14 }}>
          <input type="checkbox" checked={db.enabled} disabled={!db.host} onChange={(e) => up({ enabled: e.target.checked })} />
          <span>Store <b>new</b> analyses in my FalkorDB. (Already-analysed repos stay where they were created; the connection is needed to open the ones in your database.)</span>
        </label>
        <label className="check-row" style={{ marginTop: 8 }}>
          <input type="checkbox" checked={db.remember} onChange={(e) => up({ remember: e.target.checked })} />Remember this connection in this browser (localStorage, unencrypted: not on a shared computer)
        </label>
        <div className="banner info" style={{ marginTop: 14, fontSize: 12.5 }}>
          {privateAllowed ? 'This server allows private addresses (self-hosted).' : 'Your FalkorDB must be reachable from this server over the public internet: private, loopback and cloud-metadata addresses are refused. Allow-list this server\'s IP in your firewall, and prefer TLS.'}
          {' '}Deleting a workspace while connected also removes its graph from your database; automatic expiry only removes our record.
        </div>
      </div>
    </div>
  )
}
