import type { Metadata } from 'next'
import SectionWrapper from '@/components/marketing/section-wrapper'
import WaitlistForm from '@/components/marketing/waitlist-form'
import {
  Calculator,
  AlertTriangle,
  Globe,
  ArrowRight,
  Wallet,
  Search,
  Brain,
  FileText,
  Download,
  Send,
} from 'lucide-react'

export const metadata: Metadata = {
  title: 'CRA Compliance - Axiom',
  description:
    'ACB method, superficial loss with proration, CARF 2026 readiness. How Axiom handles Canadian crypto tax law.',
  openGraph: {
    title: 'CRA Compliance - Axiom',
    description:
      'ACB method, superficial loss with proration, CARF 2026 readiness. How Axiom handles Canadian crypto tax law.',
    type: 'website',
    locale: 'en_CA',
  },
  twitter: { card: 'summary_large_image' },
}

const filingSteps = [
  {
    icon: Wallet,
    title: 'Connect your wallets',
    description: 'Add your wallet addresses: NEAR, Ethereum, Polygon, and more.',
  },
  {
    icon: Search,
    title: 'Axiom indexes transactions',
    description:
      'On-chain transactions are pulled directly from the blockchain. Exchange data can be imported via CSV.',
  },
  {
    icon: Brain,
    title: 'Classifications are applied',
    description:
      'AI classifies trades, transfers, staking rewards, and DeFi interactions automatically.',
  },
  {
    icon: Calculator,
    title: 'Reports generated',
    description:
      'ACB calculations, capital gains/losses, income summaries, all computed per CRA rules.',
  },
  {
    icon: Download,
    title: 'Download your tax package',
    description:
      'Export your complete CRA-ready tax package as CSV or PDF.',
  },
  {
    icon: Send,
    title: 'Send to your accountant',
    description:
      'Hand off a clean, accurate, defensible tax package. Your accountant will thank you.',
  },
]

export default function CompliancePage() {
  return (
    <>
      {/* Hero */}
      <SectionWrapper aria-label="Compliance overview">
        <div className="flex flex-col md:flex-row items-center gap-8 md:gap-16">
          <div className="max-w-xl">
            <h1 className="text-4xl md:text-6xl font-bold mb-6">
              <span className="gradient-text">
                Built for Canada. CRA-ready on day one.
              </span>
            </h1>
            <p className="text-base text-muted-foreground">
              Axiom implements Canadian crypto tax law correctly. Not adapted from a
              US product. Not approximated. Built from the ground up for the CRA.
            </p>
          </div>
          <div className="shrink-0">
            <img
              src="/illustrations/tax-report.svg"
              alt="CRA-compliant tax report with capital gains, ACB summary, and verification"
              width={280}
              height={320}
              className="w-48 md:w-56 h-auto"
            />
          </div>
        </div>
      </SectionWrapper>

      {/* CRA ACB Method */}
      <SectionWrapper aria-label="Adjusted Cost Base method">
        <div className="flex items-start gap-4 mb-6">
          <div className="flex-shrink-0 w-12 h-12 rounded-lg bg-indigo-500/10 flex items-center justify-center">
            <Calculator className="w-6 h-6 text-indigo-400" />
          </div>
          <div>
            <h2 className="text-2xl md:text-3xl font-bold mb-4">
              The CRA ACB Method
            </h2>
            <p className="text-base text-muted-foreground max-w-2xl mb-4">
              The CRA requires the{' '}
              <strong>Adjusted Cost Base (ACB)</strong> method, the average
              price you paid across all units of each cryptocurrency. Unlike
              FIFO (First In, First Out) or LIFO (Last In, First Out) used in
              some other countries, Canada uses the average cost method.
            </p>
            <p className="text-base text-muted-foreground max-w-2xl mb-4">
              This means every purchase of a cryptocurrency adjusts the average
              cost of all units you hold. When you dispose of crypto (sell,
              trade, or spend), your capital gain or loss is calculated against
              this average cost.
            </p>
            <p className="text-base text-muted-foreground max-w-2xl">
              <strong>Axiom calculates ACB automatically</strong> across all
              your wallets and exchanges. Every acquisition is tracked, every
              disposal calculated, every balance reconciled.
            </p>
          </div>
        </div>
      </SectionWrapper>

      {/* Superficial Loss Rule */}
      <SectionWrapper aria-label="Superficial loss rule">
        <div className="flex items-start gap-4 mb-6">
          <div className="flex-shrink-0 w-12 h-12 rounded-lg bg-indigo-500/10 flex items-center justify-center">
            <AlertTriangle className="w-6 h-6 text-indigo-400" />
          </div>
          <div>
            <h2 className="text-2xl md:text-3xl font-bold mb-4">
              Superficial Loss Rule
            </h2>
            <p className="text-base text-muted-foreground max-w-2xl mb-4">
              When you sell crypto at a loss and repurchase the same
              cryptocurrency within 30 days (before or after the sale), the CRA
              may deny the loss deduction. This is called a{' '}
              <strong>superficial loss</strong>.
            </p>
            <p className="text-base text-muted-foreground max-w-2xl mb-4">
              The denied loss is not gone forever. It gets added to the ACB of
              the repurchased units. But getting this wrong means overstating
              your capital losses, which the CRA will catch.
            </p>
            <p className="text-base text-muted-foreground max-w-2xl">
              <strong>Axiom detects superficial losses automatically</strong>{' '}
              with proration, splitting the denied loss proportionally when you
              repurchase fewer units than you sold. Most platforms either ignore
              this rule entirely or apply it incorrectly.
            </p>
          </div>
        </div>
      </SectionWrapper>

      {/* CARF 2026 */}
      <SectionWrapper aria-label="CARF 2026 readiness">
        <div className="flex items-start gap-4 mb-6">
          <div className="flex-shrink-0 w-12 h-12 rounded-lg bg-indigo-500/10 flex items-center justify-center">
            <Globe className="w-6 h-6 text-indigo-400" />
          </div>
          <div>
            <h2 className="text-2xl md:text-3xl font-bold mb-4">
              CARF 2026
            </h2>
            <p className="text-base text-muted-foreground max-w-2xl mb-4">
              The{' '}
              <strong>
                Crypto-Asset Reporting Framework (CARF)
              </strong>{' '}
              takes effect in 2026, requiring exchanges and platforms to report
              crypto transactions to tax authorities, similar to how banks
              report interest income today.
            </p>
            <p className="text-base text-muted-foreground max-w-2xl mb-4">
              This means the CRA will have independent data about your crypto
              activity. Discrepancies between what you report and what exchanges
              report will trigger audits.
            </p>
            <p className="text-base text-muted-foreground max-w-2xl">
              <strong>
                Axiom is built with CARF compliance in mind from day one.
              </strong>{' '}
              Every transaction is tracked, every disposition recorded, every
              cost basis calculated. When CARF reporting begins, your records
              will match.
            </p>
          </div>
        </div>
      </SectionWrapper>

      {/* Tax Year Filing Steps */}
      <SectionWrapper aria-label="Filing workflow">
        <h2 className="text-2xl md:text-3xl font-bold mb-4">
          From wallet to tax report
        </h2>
        <p className="text-base text-muted-foreground max-w-2xl mb-8">
          Six steps to a complete, CRA-ready tax package.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filingSteps.map((step, index) => (
            <div
              key={step.title}
              className="border border-border rounded-lg p-6 bg-card relative"
            >
              <div className="flex items-center gap-3 mb-3">
                <div className="w-8 h-8 rounded-full bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center">
                  <span className="text-xs font-bold text-indigo-400">
                    {index + 1}
                  </span>
                </div>
                <step.icon className="w-5 h-5 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold mb-2">{step.title}</h3>
              <p className="text-sm text-muted-foreground">
                {step.description}
              </p>
              {index < filingSteps.length - 1 && (
                <div className="hidden lg:block absolute -right-3 top-1/2 -translate-y-1/2">
                  <ArrowRight className="w-5 h-5 text-muted-foreground/30" />
                </div>
              )}
            </div>
          ))}
        </div>
      </SectionWrapper>

      {/* Bottom CTA */}
      <SectionWrapper aria-label="Get started">
        <div className="text-center max-w-xl mx-auto">
          <h2 className="text-2xl md:text-3xl font-bold mb-4">
            Stop guessing. Start filing with confidence.
          </h2>
          <p className="text-base text-muted-foreground mb-8">
            Join the waitlist for CRA-compliant crypto tax reporting.
          </p>
          <WaitlistForm variant="standalone" />
        </div>
      </SectionWrapper>
    </>
  )
}
