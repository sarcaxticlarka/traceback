const j = async (url, opts) => {
  const r = await fetch(url, opts)
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`)
  return r.json()
}
const post = (body) => ({ method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
const q = (o) => new URLSearchParams(o).toString()

export const api = {
  health: () => j('/api/health'),
  alerts: (tenant) => j(`/api/alerts?${q({ tenant })}`),
  run: (body) => j('/api/run', post(body)),
  ask: (body) => j('/api/ask', post(body)),
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
