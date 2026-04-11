'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { ExternalLink } from 'lucide-react'

interface BreachIncident {
  company: string
  date: string
  description: string
  usersAffected: string
  source: string
  sourceLabel: string
}

const breachIncidents: BreachIncident[] = [
  {
    company: 'CoinTracker',
    date: 'December 2022',
    description:
      'Customer data exposed via compromised Twilio/SendGrid integration',
    usersAffected: 'Unknown',
    source: 'https://haveibeenpwned.com/PwnedWebsites#CoinTracker',
    sourceLabel: 'Have I Been Pwned',
  },
  {
    company: 'CoinTracker',
    date: 'November 2024',
    description: 'Second data breach affecting user accounts',
    usersAffected: 'Unknown',
    source: 'https://haveibeenpwned.com/PwnedWebsites#CoinTracker',
    sourceLabel: 'Have I Been Pwned',
  },
  {
    company: 'Koinly',
    date: 'December 2024',
    description: 'User data breach disclosed',
    usersAffected: 'Unknown',
    source: 'https://haveibeenpwned.com/PwnedWebsites#Koinly',
    sourceLabel: 'Have I Been Pwned',
  },
  {
    company: 'Waltio',
    date: 'January 2025',
    description: 'French crypto tax platform data breach',
    usersAffected: 'Unknown',
    source: 'https://haveibeenpwned.com/PwnedWebsites#Waltio',
    sourceLabel: 'Have I Been Pwned',
  },
]

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
}

const itemVariants = {
  hidden: { opacity: 0, x: -20 },
  show: { opacity: 1, x: 0, transition: { duration: 0.5, ease: 'easeOut' as const } },
}

export default function BreachTimeline() {
  const shouldReduceMotion = useReducedMotion()

  return (
    <div>
      <h2 className="text-2xl md:text-3xl font-bold mb-4">
        Why your data provider&apos;s cloud matters
      </h2>
      <p className="text-muted-foreground text-base mb-8 max-w-2xl">
        The platforms you trust with your complete financial history have been
        breached. Repeatedly.
      </p>

      {shouldReduceMotion ? (
        <div className="relative border-l-2 border-destructive/30 ml-4 pl-8 space-y-8">
          {breachIncidents.map((incident) => (
            <IncidentCard key={`${incident.company}-${incident.date}`} incident={incident} />
          ))}
        </div>
      ) : (
        <motion.div
          className="relative border-l-2 border-destructive/30 ml-4 pl-8 space-y-8"
          variants={containerVariants}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-50px' }}
        >
          {breachIncidents.map((incident) => (
            <motion.div
              key={`${incident.company}-${incident.date}`}
              variants={itemVariants}
            >
              <IncidentCard incident={incident} />
            </motion.div>
          ))}
        </motion.div>
      )}

      <p className="text-sm text-muted-foreground mt-8">
        Sources linked. Data from public disclosures and HaveIBeenPwned.
      </p>
    </div>
  )
}

function IncidentCard({ incident }: { incident: BreachIncident }) {
  return (
    <div className="relative">
      {/* Timeline dot */}
      <div className="absolute -left-[calc(2rem+5px)] top-1 w-3 h-3 rounded-full bg-destructive/60 border-2 border-destructive" />

      <div className="space-y-2">
        <span className="text-sm text-destructive font-medium">
          {incident.date}
        </span>
        <h3 className="text-lg font-semibold">{incident.company}</h3>
        <p className="text-muted-foreground text-base">
          {incident.description}
        </p>
        {incident.usersAffected !== 'Unknown' && (
          <p className="text-sm text-muted-foreground">
            Users affected: {incident.usersAffected}
          </p>
        )}
        <a
          href={incident.source}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-sm text-indigo-400 hover:text-indigo-300 transition-colors"
        >
          Source: {incident.sourceLabel}
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    </div>
  )
}
