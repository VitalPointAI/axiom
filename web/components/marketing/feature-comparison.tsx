'use client'

import { Check, X, Minus } from 'lucide-react'

interface CellValue {
  type: 'yes' | 'no' | 'partial' | 'text'
  label?: string
}

const features: { name: string; axiom: CellValue; privateacb: CellValue; cointracker: CellValue; koinly: CellValue }[] = [
  {
    name: 'CRA ACB Method',
    axiom: { type: 'yes' },
    privateacb: { type: 'yes' },
    cointracker: { type: 'yes' },
    koinly: { type: 'yes' },
  },
  {
    name: 'Superficial Loss (with proration)',
    axiom: { type: 'yes' },
    privateacb: { type: 'partial', label: 'Manual' },
    cointracker: { type: 'partial', label: 'Partial' },
    koinly: { type: 'partial', label: 'Partial' },
  },
  {
    name: 'CARF 2026 Ready',
    axiom: { type: 'yes' },
    privateacb: { type: 'no' },
    cointracker: { type: 'partial', label: 'Unknown' },
    koinly: { type: 'partial', label: 'Unknown' },
  },
  {
    name: 'Direct Blockchain Indexing',
    axiom: { type: 'yes' },
    privateacb: { type: 'text', label: 'No (CSV only)' },
    cointracker: { type: 'yes' },
    koinly: { type: 'yes' },
  },
  {
    name: 'DeFi-Native Capture',
    axiom: { type: 'yes' },
    privateacb: { type: 'no' },
    cointracker: { type: 'partial', label: 'Partial' },
    koinly: { type: 'partial', label: 'Partial' },
  },
  {
    name: 'AI-Powered Classification',
    axiom: { type: 'yes' },
    privateacb: { type: 'no' },
    cointracker: { type: 'no' },
    koinly: { type: 'no' },
  },
  {
    name: 'Canadian-Hosted Data',
    axiom: { type: 'yes' },
    privateacb: { type: 'text', label: 'Yes (local)' },
    cointracker: { type: 'text', label: 'No (US)' },
    koinly: { type: 'text', label: 'No (UK)' },
  },
  {
    name: 'No Third-Party Analytics',
    axiom: { type: 'yes' },
    privateacb: { type: 'text', label: 'Yes (local)' },
    cointracker: { type: 'no' },
    koinly: { type: 'no' },
  },
  {
    name: 'Data Breach History',
    axiom: { type: 'text', label: 'None' },
    privateacb: { type: 'text', label: 'None' },
    cointracker: { type: 'text', label: '2 incidents' },
    koinly: { type: 'text', label: '1 incident' },
  },
]

function CellDisplay({ value }: { value: CellValue }) {
  switch (value.type) {
    case 'yes':
      return (
        <span className="inline-flex items-center justify-center">
          <Check className="h-5 w-5 text-green-500" aria-label="Yes" />
        </span>
      )
    case 'no':
      return (
        <span className="inline-flex items-center justify-center">
          <X className="h-5 w-5 text-muted-foreground" aria-label="No" />
        </span>
      )
    case 'partial':
      return (
        <span className="inline-flex items-center gap-1 text-orange-400">
          <Minus className="h-4 w-4" aria-hidden="true" />
          <span className="text-sm">{value.label}</span>
        </span>
      )
    case 'text': {
      const isDestructive = value.label?.includes('incident')
      return (
        <span className={`text-sm ${isDestructive ? 'text-destructive font-medium' : 'text-muted-foreground'}`}>
          {value.label}
        </span>
      )
    }
  }
}

export default function FeatureComparison() {
  return (
    <div className="w-full">
      <div className="overflow-x-auto -mx-4 md:mx-0">
        <table className="w-full min-w-[640px] text-left border-collapse">
          <thead>
            <tr>
              <th className="py-3 px-4 text-sm font-semibold text-muted-foreground border-b border-border">
                Feature
              </th>
              <th className="py-3 px-4 text-sm font-semibold text-white text-center bg-indigo-500 rounded-t-lg border-b border-indigo-400">
                Axiom
              </th>
              <th className="py-3 px-4 text-sm font-semibold text-muted-foreground text-center border-b border-border">
                PrivateACB
              </th>
              <th className="py-3 px-4 text-sm font-semibold text-muted-foreground text-center border-b border-border">
                CoinTracker
              </th>
              <th className="py-3 px-4 text-sm font-semibold text-muted-foreground text-center border-b border-border">
                Koinly
              </th>
            </tr>
          </thead>
          <tbody>
            {features.map((feature) => (
              <tr key={feature.name} className="border-b border-border last:border-b-0">
                <td className="py-3 px-4 text-sm font-medium">{feature.name}</td>
                <td className="py-3 px-4 text-center bg-indigo-500/5">
                  <CellDisplay value={feature.axiom} />
                </td>
                <td className="py-3 px-4 text-center">
                  <CellDisplay value={feature.privateacb} />
                </td>
                <td className="py-3 px-4 text-center">
                  <CellDisplay value={feature.cointracker} />
                </td>
                <td className="py-3 px-4 text-center">
                  <CellDisplay value={feature.koinly} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground mt-4 text-center">
        Comparison based on publicly available information as of 2026.
      </p>
    </div>
  )
}
