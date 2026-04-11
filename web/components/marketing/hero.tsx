'use client'

import { motion, useReducedMotion } from 'framer-motion'
import Link from 'next/link'
import WaitlistForm from './waitlist-form'
import { Button } from '@/components/ui/button'

export default function Hero() {
  const shouldReduceMotion = useReducedMotion()

  const content = (
    <div className="relative z-10 max-w-[1200px] mx-auto px-4 md:px-6 lg:px-8 text-center">
      <h1 className="text-4xl md:text-6xl font-bold leading-[1.1] mb-6">
        <span className="gradient-text">
          Canadian-sovereign, blockchain-native crypto tax reporting.
        </span>
      </h1>

      <p className="text-base text-muted-foreground max-w-2xl mx-auto mb-8">
        CRA-compliant ACB calculations. Direct blockchain indexing. Your data stays in Canada.
      </p>

      <div className="max-w-md mx-auto mb-6">
        <WaitlistForm variant="inline" />
      </div>

      <Link href="/features">
        <Button variant="outline" size="lg">
          See how Axiom works
        </Button>
      </Link>
    </div>
  )

  return (
    <section className="relative min-h-[80vh] flex items-center justify-center py-16 xl:py-24 overflow-hidden">
      {/* Background glow */}
      <div className="absolute inset-0 glow-bg" aria-hidden="true" />

      {/* Content with optional motion */}
      {shouldReduceMotion ? (
        content
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
        >
          {content}
        </motion.div>
      )}
    </section>
  )
}
