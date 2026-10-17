/* ---- bring your own FalkorDB: the connection travels per request, only for datasets that live in the user's database ---- */
let byoConn = null            // {host, port, password, ssl} while the user has one configured
let byoUseForNew = false      // "store new analyses in my FalkorDB"
let byoTenants = new Set()
let byoIds = new Set()
export const setByo = (conn, useForNew, tenants, ids) => { byoConn = conn; byoUseForNew = !!useForNew; byoTenants = new Set(tenants); byoIds = new Set(ids) }
const byoHeader = (conn) => ({ 'X-FalkorDB': btoa(JSON.stringify({ host: conn.host, port: Number(conn.port) || 6379, password: conn.password || '', ssl: !!conn.ssl })) })
function byoFor(url, opts) {
  if (!byoConn) return null
  const u = new URL(url, window.location.origin)
  if (/^\/api\/workspaces\/(github|upload|bundle)$/.test(u.pathname)) return byoUseForNew ? byoHeader(byoConn) : null
  const tenant = u.searchParams.get('tenant')
  if (tenant && byoTenants.has(tenant)) return byoHeader(byoConn)
  const m = u.pathname.match(/^\/api\/workspaces\/([0-9a-f]{8})/)
  if (m && byoIds.has(m[1])) return byoHeader(byoConn)
  if (typeof opts?.body === 'string') { try { if (byoTenants.has(JSON.parse(opts.body).tenant)) return byoHeader(byoConn) } catch { /* not json */ } }
  return null
}

const j = async (url, opts = {}) => {
  const extra = byoFor(url, opts)
  if (extra) opts = { ...opts, headers: { ...(opts.headers || {}), ...extra } }
  const r = await fetch(url, opts)
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`)
  return r.json()
}
const post = (body) => ({ method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
const q = (o) => new URLSearchParams(o).toString()

/** User-supplied provider keys travel in a header (base64 JSON), per request; the server never stores them. */
const llmHeader = (configs) => {
  const usable = (configs || []).filter((c) => c.api_key)
  if (!usable.length) return {}
  return { 'X-LLM-Providers': btoa(unescape(encodeURIComponent(JSON.stringify(usable)))) }
}
const postH = (body, configs) => {
  const base = post(body)
  return { ...base, headers: { ...base.headers, ...llmHeader(configs) } }
}

const upload = (url, form) => j(url, { method: 'POST', body: form })

export const api = {
  benchReal: () => j('/api/bench/real'),
  wsGithub: (url) => j('/api/workspaces/github', post({ url })),
  wsUpload: (file, label) => { const f = new FormData(); f.append('file', file, file.name || 'upload.zip'); f.append('label', label || ''); return upload('/api/workspaces/upload', f) },
  wsBundle: (data) => j('/api/workspaces/bundle', post(data)),
  wsGet: (id) => j(`/api/workspaces/${id}`),
  wsList: (ids) => (ids.length ? j(`/api/workspaces?${q({ ids: ids.join(',') })}`) : Promise.resolve([])),
  wsDelete: (id) => j(`/api/workspaces/${id}`, { method: 'DELETE' }),
  wsModules: (id) => j(`/api/workspaces/${id}/modules`),
  wsCommits: (id) => j(`/api/workspaces/${id}/commits?limit=60`),
  wsBenchmark: (id) => j(`/api/workspaces/${id}/benchmark`, { method: 'POST' }),
  wsBenchmarkCached: (id) => j(`/api/workspaces/${id}/benchmark`),
  tool: (tenant, tool, args = {}) => j('/api/tool', post({ tenant, tool, args })),
  impact: (tenant, body) => j('/api/impact', post({ tenant, ...body })),
  provenance: (tenant, edgeId) => j(`/api/provenance?${q({ tenant, edge_id: edgeId })}`),
  health: () => j('/api/health'),
  alerts: (tenant) => j(`/api/alerts?${q({ tenant })}`),
  run: (body, configs) => j('/api/run', postH(body, configs)),
  ask: (body, configs) => j('/api/ask', postH(body, configs)),
  dbTest: (conn) => j('/api/db/test', { method: 'POST', headers: byoHeader(conn) }),
  evidenceBundle: (tenant, claims) => j('/api/evidence-bundle', post({ tenant, claims })),
  audit: (tenant, claims, configs) => j('/api/audit', postH({ tenant, claims }, configs)),
  llmProviders: () => j('/api/llm/providers'),
  llmTest: (configs) => j('/api/llm/test', { method: 'POST', headers: llmHeader(configs) }),
  verify: (tenant, claims) => j('/api/verify', post({ tenant, claims })),
  subgraph: (tenant, edgeIds, nodeIds = []) =>
    j(`/api/subgraph?${q({ tenant, edge_ids: edgeIds.join(','), node_ids: nodeIds.join(',') })}`),
  serviceMap: (tenant) => j(`/api/graph/services?${q({ tenant })}`),
  overview: (tenant) => j(`/api/graph/overview?${q({ tenant })}`),
  runbooks: (tenant) => j(`/api/memory/runbooks?${q({ tenant })}`),
  facts: (tenant) => j(`/api/memory/facts?${q({ tenant })}`),
  episodes: (tenant) => j(`/api/memory/episodes?${q({ tenant })}`),
  learning: (tenant) => j(`/api/sim/learning?${q({ tenant })}`),
  runLearning: (tenant, n = 240) => j('/api/sim/learning', post({ tenant, n })),
  approve: (tenant, id) => j(`/api/actions/${encodeURIComponent(id)}/approve`, post({ tenant })),
  evalResults: () => j('/api/eval'),
  isolation: () => j('/api/isolation', { method: 'POST' }),
  bench: () => j('/api/bench'),
  tools: () => j('/api/tools'),
  reseed: (tenant) => j(`/api/admin/reseed?${q({ tenant })}`, { method: 'POST' }),
}
