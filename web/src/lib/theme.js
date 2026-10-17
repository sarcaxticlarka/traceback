import { useEffect, useState } from 'react'

const KEY = 'traceback.theme'
export function useTheme() {
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem(KEY) || 'auto' } catch { return 'auto' } })
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'auto') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', theme)
    try { theme === 'auto' ? localStorage.removeItem(KEY) : localStorage.setItem(KEY, theme) } catch { /* ignore */ }
  }, [theme])
  const dark = theme === 'dark' || (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  return { theme, dark, toggle: () => setTheme(dark ? 'light' : 'dark') }
}
