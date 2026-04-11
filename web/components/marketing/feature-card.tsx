'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { Card, CardContent } from '@/components/ui/card'
import type { LucideIcon } from 'lucide-react'

interface FeatureCardProps {
  icon: LucideIcon
  title: string
  description: string
}

const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' as const } },
}

export default function FeatureCard({ icon: Icon, title, description }: FeatureCardProps) {
  const shouldReduceMotion = useReducedMotion()

  const cardContent = (
    <Card className="h-full transition-all duration-200 hover:scale-[1.02] hover:shadow-lg hover:shadow-indigo-500/5">
      <CardContent className="pt-6">
        <div className="bg-indigo-500/10 text-indigo-500 p-2 rounded-lg w-fit mb-4">
          <Icon className="h-6 w-6" />
        </div>
        <h3 className="text-lg font-semibold mb-2">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  )

  if (shouldReduceMotion) {
    return <div>{cardContent}</div>
  }

  return (
    <motion.div variants={cardVariants}>
      {cardContent}
    </motion.div>
  )
}

export { cardVariants }
