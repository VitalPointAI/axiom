'use client'

import { motion, useReducedMotion } from 'framer-motion'

interface SectionWrapperProps {
  children: React.ReactNode
  className?: string
  id?: string
  'aria-label'?: string
}

export default function SectionWrapper({
  children,
  className = '',
  id,
  'aria-label': ariaLabel,
}: SectionWrapperProps) {
  const shouldReduceMotion = useReducedMotion()

  if (shouldReduceMotion) {
    return (
      <section
        id={id}
        aria-label={ariaLabel}
        className={`py-16 md:py-24 ${className}`}
      >
        <div className="max-w-[1200px] mx-auto px-4 md:px-6 lg:px-8">
          {children}
        </div>
      </section>
    )
  }

  return (
    <motion.section
      id={id}
      aria-label={ariaLabel}
      className={`py-16 md:py-24 ${className}`}
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-100px' }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
    >
      <div className="max-w-[1200px] mx-auto px-4 md:px-6 lg:px-8">
        {children}
      </div>
    </motion.section>
  )
}
