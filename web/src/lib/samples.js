/** Suggested questions built from a repository's real modules (sorted by dependents). */
export function sampleQuestions(mods) {
  const top = mods[0], second = mods[1], withDeps = mods.find((m) => m.dependencies > 0)
  if (!top) return undefined
  const s = [`Which modules import ${top.name} directly?`, `What is the full blast radius if ${top.name} fails?`, `Who made the most commits to ${top.name}?`]
  if (second) s.push(`Which team owns ${second.name} today?`)
  if (withDeps) s.push(`Which modules does ${withDeps.name} directly depend on?`)
  return s
}
