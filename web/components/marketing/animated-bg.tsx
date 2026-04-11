'use client'

import { useEffect, useRef } from 'react'

export default function AnimatedBg() {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    // Respect reduced motion preference
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (mq.matches) return

    let frame: number
    let t = 0

    function animate() {
      t += 0.003
      const x = Math.sin(t * 0.7) * 80
      const y = Math.cos(t * 0.5) * 60
      const s = 1 + Math.sin(t * 0.3) * 0.05
      el!.style.transform = `translate(${x}px, ${y}px) scale(${s})`
      frame = requestAnimationFrame(animate)
    }

    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [])

  return (
    <div
      ref={ref}
      className="fixed inset-0 pointer-events-none"
      aria-hidden="true"
      style={{
        background: [
          'radial-gradient(ellipse 900px 700px at 25% 15%, rgba(99,102,241,0.28) 0%, transparent 70%)',
          'radial-gradient(ellipse 700px 700px at 75% 55%, rgba(139,92,246,0.20) 0%, transparent 70%)',
          'radial-gradient(ellipse 600px 500px at 45% 85%, rgba(6,182,212,0.16) 0%, transparent 70%)',
        ].join(', '),
        willChange: 'transform',
      }}
    />
  )
}
