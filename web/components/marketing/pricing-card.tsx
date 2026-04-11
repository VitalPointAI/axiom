'use client'

import { Check } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const included = [
  'All supported blockchains',
  'Unlimited wallets & exchanges',
  'CRA-ready tax reports',
  'AI-powered classification',
  'Canadian-hosted data',
]

export default function PricingCard() {
  const scrollToWaitlist = () => {
    const el = document.getElementById('waitlist')
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <Card className="max-w-md mx-auto border border-border shadow-lg">
      <CardHeader className="text-center pb-2">
        <Badge variant="secondary" className="w-fit mx-auto mb-4">
          Simple pricing
        </Badge>
        <h3 className="text-2xl md:text-3xl font-bold mb-2">
          One price. One tax year. No surprises.
        </h3>
      </CardHeader>
      <CardContent className="text-center">
        <div className="mb-6">
          <span className="text-5xl font-bold">$149</span>
          <span className="text-lg text-muted-foreground">/year</span>
        </div>
        <ul className="space-y-3 text-left mb-8">
          {included.map((item) => (
            <li key={item} className="flex items-center gap-3 text-sm">
              <Check className="h-4 w-4 text-green-500 flex-shrink-0" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
        <Button
          onClick={scrollToWaitlist}
          className="w-full bg-indigo-500 hover:bg-indigo-600 text-white min-h-[44px]"
          size="lg"
        >
          Join the waitlist
        </Button>
      </CardContent>
    </Card>
  )
}
