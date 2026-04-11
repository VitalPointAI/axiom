'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { Shield, Zap, Bot, Lock, BarChart3, Globe, KeyRound } from 'lucide-react'
import FeatureCard from '@/components/marketing/feature-card'

const features = [
  {
    icon: Shield,
    title: 'CRA-Compliant from Day One',
    description:
      'ACB (Adjusted Cost Base \u2014 the average price you paid for all units of a coin) calculated automatically with superficial loss proration and CARF 2026 readiness.',
  },
  {
    icon: Zap,
    title: 'Direct Blockchain Indexing',
    description:
      'We read the blockchain directly for on-chain transactions. CSV import available for centralized exchanges without APIs.',
  },
  {
    icon: Bot,
    title: 'AI-Powered Classification',
    description:
      'Machine learning classifies your transactions automatically \u2014 trades, staking rewards, transfers, DeFi interactions \u2014 with confidence scoring.',
  },
  {
    icon: Lock,
    title: 'Post-Quantum Encrypted',
    description:
      'AES-256 encryption with quantum-resistant key exchange. Your tax data is encrypted at rest and in transit with cryptography built to withstand future threats.',
  },
  {
    icon: KeyRound,
    title: 'Zero-Knowledge Architecture',
    description:
      'Client-side computation keeps your raw data in your browser. Passkey-derived encryption keys mean even Axiom cannot access your information without your physical key.',
  },
  {
    icon: BarChart3,
    title: 'Complete Tax Reports',
    description:
      'Capital gains, income summary, T1135 check, Koinly export, accountant-ready PDF package. Everything your accountant needs.',
  },
  {
    icon: Globe,
    title: 'Multi-Chain Support',
    description:
      'NEAR, Ethereum, Polygon, XRP, and Akash. One platform for all your crypto tax obligations.',
  },
]

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
}

export default function FeatureGrid() {
  const shouldReduceMotion = useReducedMotion()

  if (shouldReduceMotion) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {features.map((feature) => (
          <FeatureCard key={feature.title} {...feature} />
        ))}
      </div>
    )
  }

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true }}
      className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
    >
      {features.map((feature) => (
        <FeatureCard key={feature.title} {...feature} />
      ))}
    </motion.div>
  )
}
