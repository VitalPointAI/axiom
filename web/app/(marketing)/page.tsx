import type { Metadata } from 'next'

import Hero from '@/components/marketing/hero'
import SectionWrapper from '@/components/marketing/section-wrapper'
import FeatureComparison from '@/components/marketing/feature-comparison'
import ChainShowcase from '@/components/marketing/chain-showcase'
import PricingCard from '@/components/marketing/pricing-card'
import WaitlistForm from '@/components/marketing/waitlist-form'
import FeatureGrid from './feature-grid'

export const metadata: Metadata = {
  title: 'Axiom - Canadian Crypto Tax Platform',
  description:
    'Privacy-preserving, blockchain-native Canadian crypto tax reporting. Post-quantum encryption. Your data never leaves Canada.',
  openGraph: {
    title: 'Axiom - Canadian Crypto Tax Platform',
    description:
      'Privacy-preserving, blockchain-native Canadian crypto tax reporting.',
    type: 'website',
    locale: 'en_CA',
  },
  twitter: { card: 'summary_large_image' },
}

export default function LandingPage() {
  return (
    <>
      {/* Hero - no SectionWrapper, has its own layout */}
      <Hero />

      {/* Features */}
      <SectionWrapper id="features" aria-label="Why Axiom">
        <h2 className="text-2xl md:text-3xl font-bold text-center mb-12">
          Why Axiom
        </h2>
        <FeatureGrid />
      </SectionWrapper>

      {/* Chain Showcase */}
      <SectionWrapper aria-label="Multi-chain support">
        <h2 className="text-2xl md:text-3xl font-bold text-center mb-8">
          We read the blockchain directly. Exchange CSVs when you need them.
        </h2>
        <ChainShowcase />
      </SectionWrapper>

      {/* Comparison */}
      <SectionWrapper id="comparison" aria-label="How Axiom compares">
        <h2 className="text-2xl md:text-3xl font-bold text-center mb-12">
          How Axiom compares
        </h2>
        <FeatureComparison />
      </SectionWrapper>

      {/* Pricing */}
      <SectionWrapper id="pricing" aria-label="Pricing">
        <PricingCard />
      </SectionWrapper>

      {/* Privacy Teaser */}
      <SectionWrapper aria-label="Privacy">
        <div className="text-center max-w-2xl mx-auto">
          <h2 className="text-2xl md:text-3xl font-bold mb-4">
            Your data never leaves Canada.
          </h2>
          <p className="text-base text-muted-foreground mb-6">
            Toronto-hosted infrastructure with post-quantum encryption,
            client-side zero-knowledge computation, and passkey-derived
            encryption keys. No third-party analytics. No US or UK cloud
            providers. Private by design.
          </p>
          <a
            href="/privacy"
            className="text-indigo-500 hover:text-indigo-400 text-sm font-medium underline underline-offset-4"
          >
            Learn more about our privacy architecture
          </a>
        </div>
      </SectionWrapper>

      {/* Final CTA */}
      <SectionWrapper id="waitlist" aria-label="Join the waitlist">
        <div className="text-center max-w-md mx-auto">
          <h2 className="text-2xl md:text-3xl font-bold mb-6">
            Ready to simplify your crypto taxes?
          </h2>
          <WaitlistForm variant="standalone" />
        </div>
      </SectionWrapper>
    </>
  )
}
