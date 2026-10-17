import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp, isRepo } from '../lib/ctx'
import { sampleQuestions } from '../lib/samples'
import AskView from '../components/AskView'
import MemoryView from '../components/MemoryView'
import ProofView from '../components/ProofView'

export function AskPage() {
  const { tenant, graphOn, useLlm, userKeys } = useApp()
  const [samples, setSamples] = useState(undefined)
  useEffect(() => {
    setSamples(undefined)
    if (isRepo(tenant)) api.wsModules(tenant.slice(5)).then((m) => setSamples(sampleQuestions(m))).catch(() => {})
  }, [tenant])
  return (
    <div>
      <div className="page-head"><h2>Company brain</h2>
        <p>Ask in plain language. Questions are routed to graph tools; each answer lists the evidence behind it, next to what a documents-only reader finds in the same material.</p></div>
      <AskView key={tenant + (samples ? samples[0] : '')} tenant={tenant} graphOn={graphOn} useLlm={useLlm} keys={userKeys} samples={samples} />
    </div>
  )
}

export function MemoryPage() {
  const { tenant, memKey } = useApp()
  return (
    <div>
      <div className="page-head"><h2>Agent memory</h2>
        <p>Three kinds of memory, all in the graph: episodes (what ran), facts with validity windows that supersede each other, and runbook statistics that update after every outcome.</p></div>
      <MemoryView tenant={tenant} refreshKey={memKey} repo={isRepo(tenant)} />
    </div>
  )
}

export function ProofPage() {
  return (
    <div>
      <div className="page-head"><h2>Proof</h2>
        <p>Does the graph earn its place? Same questions, same material, with and without relationships. Plus isolation, concurrency and the full query catalogue.</p></div>
      <ProofView />
    </div>
  )
}
