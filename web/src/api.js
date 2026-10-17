const j = async (url, opts) => {
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

export const api = {
  health: () => j('/api/health'),
  alerts: (tenant) => j(`/api/alerts?${q({ tenant })}`),
  run: (body, configs) => j('/api/run', postH(body, configs)),
  ask: (body, configs) => j('/api/ask', postH(body, configs)),
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
