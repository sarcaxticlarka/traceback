import { useEffect, useState } from 'react'

/** Tiny hash router: "#/app/lab?ws=abc" -> { path: "/app/lab", query: {ws: "abc"} } */
export function parseHash(h = window.location.hash) {
  const raw = h.replace(/^#/, '') || '/'
  const [path, qs = ''] = raw.split('?')
  return { path: path || '/', query: Object.fromEntries(new URLSearchParams(qs)) }
}
export function useRoute() {
  const [route, setRoute] = useState(parseHash())
  useEffect(() => {
    const on = () => { setRoute(parseHash()); window.scrollTo({ top: 0 }) }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}
export const go = (path, query) => {
  const qs = query ? '?' + new URLSearchParams(query).toString() : ''
  window.location.hash = path + qs
}
