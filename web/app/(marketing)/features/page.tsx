import type { Metadata } from 'next'
import SectionWrapper from '@/components/marketing/section-wrapper'
import FeatureComparison from '@/components/marketing/feature-comparison'
import ChainShowcase from '@/components/marketing/chain-showcase'
import WaitlistForm from '@/components/marketing/waitlist-form'
import {
  Calculator,
  Shield,
  Zap,
  Link2,
  Brain,
  FileText,
  AlertTriangle,
  Globe,
} from 'lucide-react'

export const metadata: Metadata = {
  title: 'Features - Axiom',
  description:
    'Direct blockchain indexing, AI-powered classification, multi-chain support. See how Axiom works.',
  openGraph: {
    title: 'Features - Axiom',
    description:
      'Direct blockchain indexing, AI-powered classification, multi-chain support.',
    type: 'website',
    locale: 'en_CA',
  },
  twitter: { card: 'summary_large_image' },
}

const features = [
  {
    icon: Calculator,
    title: 'CRA ACB Compliance',
    description:
      'Adjusted Cost Base (ACB), the average price you paid across all units of each cryptocurrency, calculated automatically across all your wallets. The method the CRA requires.',
  },
  {
    icon: AlertTriangle,
    title: 'Superficial Loss with Proration',
    description:
      'When you sell crypto at a loss and repurchase within 30 days, the CRA may deny the deduction. Axiom detects these automatically, with proration when you repurchase fewer units than you sold.',
  },
  {
    icon: Shield,
    title: 'CARF 2026 Ready',
    description:
      'The Crypto-Asset Reporting Framework (CARF) takes effect in 2026, requiring platforms to report crypto transactions to tax authorities. Axiom is built with CARF compliance from day one.',
  },
  {
    icon: Link2,
    title: 'Direct Blockchain Indexing',
    description:
      'Axiom reads your on-chain transaction history directly from the blockchain. Every swap, stake, bridge, and transfer captured automatically. CSV import available for centralized exchanges without APIs.',
  },
  {
    icon: Zap,
    title: 'DeFi-Native Transaction Capture',
    description:
      'Liquidity pools, yield farming, token swaps, bridging: Axiom understands DeFi natively. Complex multi-step transactions are decomposed and classified correctly.',
  },
  {
    icon: Brain,
    title: 'AI Classification with Confidence Scoring',
    description:
      'Machine learning classifies your transactions with a confidence score. High-confidence classifications are applied automatically. Low-confidence items are flagged for your review.',
  },
  {
    icon: Globe,
    title: 'Multi-Chain Support',
    description:
      'NEAR Protocol, Ethereum, Polygon, Optimism, Cronos, Akash, XRP, and more chains coming. One platform for all your crypto tax reporting.',
  },
  {
    icon: FileText,
    title: 'Complete Tax Report Generation',
    description:
      'Capital gains and losses, income summaries, cost basis tracking. Everything your accountant needs in a CRA-ready package. Export as CSV or PDF.',
  },
]

const workflowSteps = [
  {
    step: 1,
    title: 'Connect Your Wallets',
    description:
      'Add your wallet addresses. Axiom supports NEAR, Ethereum, Polygon, and more. No private keys needed, just your public address.',
  },
  {
    step: 2,
    title: 'Automatic Indexing',
    description:
      'Axiom reads the blockchain directly. Every on-chain transaction is pulled, parsed, and stored automatically. Exchange transactions can be imported via CSV.',
  },
  {
    step: 3,
    title: 'AI Classification',
    description:
      'Transactions are automatically classified: trades, transfers, staking rewards, DeFi interactions. Each with a confidence score so you know what to review.',
  },
  {
    step: 4,
    title: 'ACB Calculation',
    description:
      'Adjusted Cost Base is computed across all wallets using the CRA-required method. Superficial losses detected and prorated automatically.',
  },
  {
    step: 5,
    title: 'Tax Reports',
    description:
      'Download your complete tax package: capital gains/losses report, income summary, and cost basis schedule. Send it to your accountant.',
  },
]

export default function FeaturesPage() {
  return (
    <>
      {/* Hero Section */}
      <SectionWrapper aria-label="Features overview">
        <div className="flex flex-col md:flex-row items-center gap-8 md:gap-16">
          <div className="max-w-xl">
            <h1 className="text-4xl md:text-6xl font-bold mb-6">
              <span className="gradient-text">Built for Canadian crypto taxes.</span>
            </h1>
            <p className="text-base text-muted-foreground">
              Direct blockchain indexing, AI-powered classification, multi-chain
              support. See how Axiom handles your crypto tax reporting from start to
              finish.
            </p>
          </div>
          <div className="shrink-0">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/illustrations/dashboard-preview.svg"
              alt="Axiom dashboard with portfolio analytics and tax reporting"
              width={400}
              height={243}
              className="w-72 md:w-96 h-auto rounded-lg border border-border/30"
            />
          </div>
        </div>
      </SectionWrapper>

      {/* Feature Grid */}
      <SectionWrapper aria-label="Feature details">
        <h2 className="text-2xl md:text-3xl font-bold mb-8">
          Everything you need for CRA-compliant crypto taxes
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature) => (
            <div
              key={feature.title}
              className="border border-border rounded-lg p-6 bg-card hover:border-indigo-500/30 transition-colors"
            >
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center mb-4">
                <feature.icon className="w-5 h-5 text-indigo-400" />
              </div>
              <h3 className="text-lg font-semibold mb-2">{feature.title}</h3>
              <p className="text-sm text-muted-foreground">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </SectionWrapper>

      {/* Automation Deep-Dive */}
      <SectionWrapper aria-label="How Axiom works">
        <h2 className="text-2xl md:text-3xl font-bold mb-4">
          We read the blockchain directly.{' '}
          <span className="gradient-text">No missing on-chain transactions.</span>
        </h2>
        <p className="text-base text-muted-foreground max-w-2xl mb-12">
          Five steps from wallet to tax report. No spreadsheets. No manual
          entry. No missing transactions.
        </p>

        <div className="space-y-6 max-w-2xl">
          {workflowSteps.map((item) => (
            <div key={item.step} className="flex gap-4">
              <div className="flex-shrink-0 w-10 h-10 rounded-full bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center">
                <span className="text-sm font-bold text-indigo-400">
                  {item.step}
                </span>
              </div>
              <div>
                <h3 className="text-lg font-semibold mb-1">{item.title}</h3>
                <p className="text-sm text-muted-foreground">
                  {item.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </SectionWrapper>

      {/* Chain Support Grid */}
      <SectionWrapper aria-label="Supported blockchains">
        <h2 className="text-2xl md:text-3xl font-bold mb-8">
          Multi-chain support
        </h2>
        <ChainShowcase />
      </SectionWrapper>

      {/* Comparison Table */}
      <SectionWrapper aria-label="Feature comparison">
        <h2 className="text-2xl md:text-3xl font-bold mb-8">
          How Axiom compares
        </h2>
        <FeatureComparison />
      </SectionWrapper>

      {/* Bottom CTA */}
      <SectionWrapper aria-label="Get started">
        <div className="text-center max-w-xl mx-auto">
          <h2 className="text-2xl md:text-3xl font-bold mb-4">
            Ready to get started?
          </h2>
          <p className="text-base text-muted-foreground mb-8">
            Join the waitlist to be among the first to try Axiom.
          </p>
          <WaitlistForm variant="standalone" />
        </div>
      </SectionWrapper>
    </>
  )
}
