'use client'

import { useEffect, useRef } from 'react'

export default function AnimatedBg() {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (mq.matches) return

    let frame: number
    let t = 0

    function animate() {
      t += 0.003
      const x = Math.sin(t * 0.7) * 100
      const y = Math.cos(t * 0.5) * 80
      el!.style.transform = `translate(${x}px, ${y}px)`
      frame = requestAnimationFrame(animate)
    }

    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [])

  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
      <div
        ref={ref}
        style={{
          position: 'absolute',
          top: '-200px',
          left: '-200px',
          right: '-200px',
          bottom: '-200px',
          background: [
            'radial-gradient(ellipse 900px 700px at 30% 20%, rgba(99,102,241,0.28) 0%, transparent 70%)',
            'radial-gradient(ellipse 700px 700px at 70% 50%, rgba(139,92,246,0.20) 0%, transparent 70%)',
            'radial-gradient(ellipse 600px 500px at 50% 80%, rgba(6,182,212,0.16) 0%, transparent 70%)',
          ].join(', '),
          willChange: 'transform',
        }}
      />
    </div>
  )
}
