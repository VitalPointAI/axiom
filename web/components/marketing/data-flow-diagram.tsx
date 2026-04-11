'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { Check, Globe, Monitor, Server } from 'lucide-react'

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
  { label: 'Price API requests (CoinGecko - anonymous)', staysLocal: false },
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
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' } },
}

function DataItemRow({ item }: { item: DataItem }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      {item.staysLocal ? (
        <Check className="w-4 h-4 text-emerald-400 flex-shrink-0" />
      ) : (
        <Globe className="w-4 h-4 text-muted-foreground flex-shrink-0" />
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
  children,
  borderColor = 'border-border',
}: {
  title: string
  subtitle?: string
  icon: typeof Monitor
  children: React.ReactNode
  borderColor?: string
}) {
  return (
    <div className={`border ${borderColor} rounded-lg p-4 md:p-6 bg-card`}>
      <div className="flex items-center gap-2 mb-4">
        <Icon className="w-5 h-5 text-muted-foreground" />
        <div>
          <h3 className="text-lg font-semibold">{title}</h3>
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
  const shouldReduceMotion = useReducedMotion()

  return (
    <div className="hidden md:block relative">
      <svg
        viewBox="0 0 900 400"
        className="w-full h-auto"
        aria-label="Data flow diagram showing what stays on the Axiom server in Toronto versus what crosses the network"
      >
        {/* Your Browser Box */}
        <rect x="20" y="50" width="220" height="300" rx="12" className="fill-card stroke-border" strokeWidth="1.5" />
        <foreignObject x="30" y="60" width="200" height="280">
          <div className="text-sm space-y-3 p-2">
            <div className="flex items-center gap-2 mb-3">
              <Monitor className="w-4 h-4 text-muted-foreground" />
              <span className="font-semibold">Your Browser</span>
            </div>
            <p className="text-xs text-muted-foreground mb-2">Data you send:</p>
            {browserToServer.map((item) => (
              <DataItemRow key={item.label} item={item} />
            ))}
          </div>
        </foreignObject>

        {/* Axiom Server Box - center, highlighted */}
        <rect x="310" y="20" width="280" height="360" rx="12" className="fill-card stroke-indigo-500/50" strokeWidth="2" />
        <foreignObject x="320" y="30" width="260" height="340">
          <div className="text-sm space-y-3 p-2">
            <div className="flex items-center gap-2 mb-2">
              <Server className="w-4 h-4 text-indigo-400" />
              <div>
                <span className="font-semibold text-indigo-400">Axiom Server</span>
                <span className="text-xs text-muted-foreground ml-1">(Toronto)</span>
              </div>
            </div>
            <div className="border border-emerald-500/30 rounded-md p-2 bg-emerald-500/5">
              <p className="text-xs text-emerald-400 font-medium mb-2">Stays local - never leaves Canada</p>
              {staysOnServer.map((item) => (
                <DataItemRow key={item.label} item={item} />
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              All stored data and processed results stay in Canada.
            </p>
          </div>
        </foreignObject>

        {/* External APIs Box */}
        <rect x="660" y="80" width="220" height="240" rx="12" className="fill-card stroke-border" strokeWidth="1.5" strokeDasharray="6 3" />
        <foreignObject x="670" y="90" width="200" height="220">
          <div className="text-sm space-y-3 p-2">
            <div className="flex items-center gap-2 mb-3">
              <Globe className="w-4 h-4 text-muted-foreground" />
              <span className="font-semibold text-muted-foreground">External APIs</span>
            </div>
            <p className="text-xs text-muted-foreground mb-2">Public data only:</p>
            {serverToExternal.map((item) => (
              <DataItemRow key={item.label} item={item} />
            ))}
            <p className="text-xs text-muted-foreground mt-3">
              No user data is sent to external services.
            </p>
          </div>
        </foreignObject>

        {/* Connection lines */}
        {/* Browser -> Server */}
        {shouldReduceMotion ? (
          <>
            <line x1="240" y1="200" x2="310" y2="200" className="stroke-indigo-500/40" strokeWidth="2" markerEnd="url(#arrowhead)" />
            {/* Server -> External */}
            <line x1="590" y1="200" x2="660" y2="200" className="stroke-muted-foreground/30" strokeWidth="1.5" strokeDasharray="6 3" markerEnd="url(#arrowhead-muted)" />
          </>
        ) : (
          <>
            <motion.line
              x1="240" y1="200" x2="310" y2="200"
              className="stroke-indigo-500/40"
              strokeWidth="2"
              initial={{ pathLength: 0 }}
              whileInView={{ pathLength: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.8, ease: 'easeOut', delay: 0.3 }}
              markerEnd="url(#arrowhead)"
            />
            <motion.line
              x1="590" y1="200" x2="660" y2="200"
              className="stroke-muted-foreground/30"
              strokeWidth="1.5"
              strokeDasharray="6 3"
              initial={{ pathLength: 0 }}
              whileInView={{ pathLength: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.8, ease: 'easeOut', delay: 0.5 }}
              markerEnd="url(#arrowhead-muted)"
            />
          </>
        )}

        {/* Arrow markers */}
        <defs>
          <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" className="fill-indigo-500/40" />
          </marker>
          <marker id="arrowhead-muted" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" className="fill-muted-foreground/30" />
          </marker>
        </defs>
      </svg>
    </div>
  )
}

function MobileDiagram() {
  return (
    <div className="md:hidden space-y-4">
      <FlowBox title="Your Browser" icon={Monitor} borderColor="border-border">
        <p className="text-xs text-muted-foreground mb-2">Data you send:</p>
        {browserToServer.map((item) => (
          <DataItemRow key={item.label} item={item} />
        ))}
      </FlowBox>

      {/* Vertical arrow */}
      <div className="flex justify-center">
        <div className="w-px h-8 bg-indigo-500/40 relative">
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[6px] border-r-[6px] border-t-[8px] border-transparent border-t-indigo-500/40" />
        </div>
      </div>

      <FlowBox
        title="Axiom Server"
        subtitle="Toronto"
        icon={Server}
        borderColor="border-indigo-500/50"
      >
        <div className="border border-emerald-500/30 rounded-md p-3 bg-emerald-500/5 mb-3">
          <p className="text-xs text-emerald-400 font-medium mb-2">
            Stays local - never leaves Canada
          </p>
          {staysOnServer.map((item) => (
            <DataItemRow key={item.label} item={item} />
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          All stored data and processed results stay in Canada.
        </p>
      </FlowBox>

      {/* Vertical arrow */}
      <div className="flex justify-center">
        <div className="w-px h-8 bg-muted-foreground/30 relative">
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[6px] border-r-[6px] border-t-[8px] border-transparent border-t-muted-foreground/30" />
        </div>
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
