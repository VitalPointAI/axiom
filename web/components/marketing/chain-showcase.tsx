'use client'

import Image from 'next/image'

interface ChainInfo {
  name: string
  logo: string
}

const chains: ChainInfo[] = [
  { name: 'NEAR', logo: '/chains/near.svg' },
  { name: 'Ethereum', logo: '/chains/ethereum.svg' },
  { name: 'Polygon', logo: '/chains/polygon.svg' },
  { name: 'XRP', logo: '/chains/xrp.svg' },
  { name: 'Akash', logo: '/chains/akash.svg' },
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
              <Image src={chain.logo} alt={`${chain.name} logo`} width={40} height={40} className="h-10 w-10" />
            </div>
            <span className="text-sm text-muted-foreground font-medium">{chain.name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
