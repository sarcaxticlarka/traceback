import { useEffect, useRef, useState } from 'react'

const reduced = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/** True once the element has scrolled into view (and stays true). */
export function useInView(threshold = 0.18) {
  const ref = useRef(null)
  const [seen, setSeen] = useState(() => reduced())
  useEffect(() => {
    if (seen || !ref.current) return undefined
    const el = ref.current
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) setSeen(true) }, { threshold })
    io.observe(el)
    // IntersectionObserver can miss an element that is jumped over entirely (scrollbar drag, End key, anchor jump):
    // anything at or above the lower part of the viewport counts as seen.
    const onScroll = () => { if (el.getBoundingClientRect().top < window.innerHeight * 0.92) setSeen(true) }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => { io.disconnect(); window.removeEventListener('scroll', onScroll) }
  }, [seen, threshold])
  return [ref, seen]
}

/** Fade-and-rise on scroll. */
export function Reveal({ children, delay = 0, as: Tag = 'div', className = '', ...rest }) {
  const [ref, seen] = useInView()
  return <Tag ref={ref} className={`lp-reveal ${seen ? 'in' : ''} ${className}`} style={{ '--d': `${delay}ms` }} {...rest}>{children}</Tag>
}

/** Number that counts up when it scrolls into view. */
export function CountUp({ to, decimals = 0, prefix = '', suffix = '', duration = 1500 }) {
  const [ref, seen] = useInView(0.4)
  const [v, setV] = useState(reduced() ? to : 0)
  useEffect(() => {
    if (!seen || reduced()) { if (seen) setV(to); return undefined }
    let raf
    const t0 = performance.now()
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / duration)
      setV(to * (1 - Math.pow(1 - p, 3)))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [seen, to, duration])
  return <span ref={ref}>{prefix}{v.toFixed(decimals)}{suffix}</span>
}

/** Cursor-following spotlight: sets --mx / --my on the element. */
export const spot = (e) => {
  const r = e.currentTarget.getBoundingClientRect()
  e.currentTarget.style.setProperty('--mx', `${e.clientX - r.left}px`)
  e.currentTarget.style.setProperty('--my', `${e.clientY - r.top}px`)
}
