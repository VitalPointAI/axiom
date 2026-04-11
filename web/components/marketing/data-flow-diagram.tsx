'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { Check, Globe, Monitor, Server, ArrowRight, ArrowDown } from 'lucide-react'

interface DataItem {
  label: string
  staysLocal: boolean
}

const browserToServer: DataItem[] = [
  { label: 'Login credentials (encrypted)', staysLocal: true },
  { label: 'Wallet addresses', staysLocal: true },
  { label: 'Report requests', staysLocal: true },
]

const serverToExternal: DataItem[] = [
  { label: 'Blockchain RPC queries (public data only)', staysLocal: false },
  { label: 'Price API requests (CoinGecko, anonymous)', staysLocal: false },
]

const staysOnServer: DataItem[] = [
  { label: 'Transaction data', staysLocal: true },
  { label: 'Classifications', staysLocal: true },
  { label: 'Tax calculations', staysLocal: true },
  { label: 'Reports', staysLocal: true },
  { label: 'User identity', staysLocal: true },
]

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.15 },
  },
}

const boxVariants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' as const } },
}

function DataItemRow({ item }: { item: DataItem }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      {item.staysLocal ? (
        <Check className="w-4 h-4 text-emerald-400 shrink-0" />
      ) : (
        <Globe className="w-4 h-4 text-muted-foreground shrink-0" />
      )}
      <span className={item.staysLocal ? 'text-foreground' : 'text-muted-foreground'}>
        {item.label}
      </span>
    </div>
  )
}

function FlowBox({
  title,
  subtitle,
  icon: Icon,
  iconColor = 'text-muted-foreground',
  children,
  borderColor = 'border-border',
  className = '',
}: {
  title: string
  subtitle?: string
  icon: typeof Monitor
  iconColor?: string
  children: React.ReactNode
  borderColor?: string
  className?: string
}) {
  return (
    <div className={`border ${borderColor} rounded-lg p-4 md:p-6 bg-card ${className}`}>
      <div className="flex items-center gap-2 mb-4">
        <Icon className={`w-5 h-5 ${iconColor}`} />
        <div>
          <h3 className="text-lg font-semibold text-foreground">{title}</h3>
          {subtitle && (
            <p className="text-sm text-muted-foreground">{subtitle}</p>
          )}
        </div>
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

function DesktopDiagram() {
  return (
    <div className="hidden md:grid grid-cols-[1fr_auto_1.2fr_auto_1fr] items-center gap-4">
      {/* Your Browser */}
      <FlowBox title="Your Browser" icon={Monitor}>
        <p className="text-xs text-muted-foreground mb-2">Data you send:</p>
        {browserToServer.map((item) => (
          <DataItemRow key={item.label} item={item} />
        ))}
      </FlowBox>

      {/* Arrow */}
      <ArrowRight className="w-6 h-6 text-indigo-500/50" />

      {/* Axiom Server */}
      <FlowBox
        title="Axiom Server"
        subtitle="Toronto"
        icon={Server}
        iconColor="text-indigo-400"
        borderColor="border-indigo-500/50"
      >
        <div className="border border-emerald-500/30 rounded-md p-3 bg-emerald-500/5">
          <p className="text-xs text-emerald-400 font-medium mb-2">
            Stays local, never leaves Canada
          </p>
          {staysOnServer.map((item) => (
            <DataItemRow key={item.label} item={item} />
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          All stored data and processed results stay in Canada.
        </p>
      </FlowBox>

      {/* Arrow */}
      <ArrowRight className="w-6 h-6 text-muted-foreground/30" />

      {/* External APIs */}
      <FlowBox
        title="External APIs"
        icon={Globe}
        borderColor="border-border border-dashed"
      >
        <p className="text-xs text-muted-foreground mb-2">Public data only:</p>
        {serverToExternal.map((item) => (
          <DataItemRow key={item.label} item={item} />
        ))}
        <p className="text-xs text-muted-foreground mt-3">
          No user data is sent to external services.
        </p>
      </FlowBox>
    </div>
  )
}

function MobileDiagram() {
  return (
    <div className="md:hidden space-y-4">
      <FlowBox title="Your Browser" icon={Monitor}>
        <p className="text-xs text-muted-foreground mb-2">Data you send:</p>
        {browserToServer.map((item) => (
          <DataItemRow key={item.label} item={item} />
        ))}
      </FlowBox>

      <div className="flex justify-center">
        <ArrowDown className="w-6 h-6 text-indigo-500/50" />
      </div>

      <FlowBox
        title="Axiom Server"
        subtitle="Toronto"
        icon={Server}
        iconColor="text-indigo-400"
        borderColor="border-indigo-500/50"
      >
        <div className="border border-emerald-500/30 rounded-md p-3 bg-emerald-500/5 mb-3">
          <p className="text-xs text-emerald-400 font-medium mb-2">
            Stays local, never leaves Canada
          </p>
          {staysOnServer.map((item) => (
            <DataItemRow key={item.label} item={item} />
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          All stored data and processed results stay in Canada.
        </p>
      </FlowBox>

      <div className="flex justify-center">
        <ArrowDown className="w-6 h-6 text-muted-foreground/30" />
      </div>

      <FlowBox
        title="External APIs"
        icon={Globe}
        borderColor="border-border border-dashed"
      >
        <p className="text-xs text-muted-foreground mb-2">Public data only:</p>
        {serverToExternal.map((item) => (
          <DataItemRow key={item.label} item={item} />
        ))}
        <p className="text-xs text-muted-foreground mt-2">
          No user data is sent to external services.
        </p>
      </FlowBox>
    </div>
  )
}

export default function DataFlowDiagram() {
  const shouldReduceMotion = useReducedMotion()

  return (
    <div>
      <h2 className="text-2xl md:text-3xl font-bold mb-4">
        See exactly where your data goes
      </h2>
      <p className="text-muted-foreground text-base mb-8 max-w-2xl">
        See exactly what stays local and what crosses the network.
      </p>

      {shouldReduceMotion ? (
        <div>
          <DesktopDiagram />
          <MobileDiagram />
        </div>
      ) : (
        <motion.div
          variants={containerVariants}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-50px' }}
        >
          <motion.div variants={boxVariants}>
            <DesktopDiagram />
            <MobileDiagram />
          </motion.div>
        </motion.div>
      )}
    </div>
  )
}
