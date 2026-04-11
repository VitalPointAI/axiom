'use client'

import { Hexagon, Circle, Pentagon, Diamond, Triangle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

interface ChainInfo {
  name: string
  icon: LucideIcon
  color: string
}

const chains: ChainInfo[] = [
  { name: 'NEAR', icon: Hexagon, color: '#00C1DE' },
  { name: 'Ethereum', icon: Diamond, color: '#627EEA' },
  { name: 'Polygon', icon: Pentagon, color: '#8247E5' },
  { name: 'XRP', icon: Circle, color: '#23292F' },
  { name: 'Akash', icon: Triangle, color: '#FF414C' },
]

export default function ChainShowcase() {
  return (
    <div className="text-center">
      <h3 className="text-2xl md:text-3xl font-bold mb-3">Multi-chain support</h3>
      <p className="text-base text-muted-foreground mb-10">
        Direct blockchain indexing across 5+ networks
      </p>
      <div className="flex flex-wrap justify-center gap-8">
        {chains.map((chain) => (
          <div key={chain.name} className="flex flex-col items-center gap-2">
            <div className="p-4 rounded-xl bg-card border border-border">
              <chain.icon className="h-10 w-10" style={{ color: chain.color }} />
            </div>
            <span className="text-sm text-muted-foreground font-medium">{chain.name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
