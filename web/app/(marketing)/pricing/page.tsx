import type { Metadata } from 'next'
import SectionWrapper from '@/components/marketing/section-wrapper'
import PricingCard from '@/components/marketing/pricing-card'
import WaitlistForm from '@/components/marketing/waitlist-form'

export const metadata: Metadata = {
  title: 'Pricing - Axiom',
  description:
    'Simple flat-fee annual pricing. One price per tax year. No tiers, no surprises.',
  openGraph: {
    title: 'Pricing - Axiom',
    description:
      'Simple flat-fee annual pricing. One price per tax year. No tiers, no surprises.',
    type: 'website',
    locale: 'en_CA',
  },
  twitter: { card: 'summary_large_image' },
}

const faqs = [
  {
    question: "What's included?",
    answer:
      'Everything: all chains, unlimited wallets, AI classification, CRA-ready reports, ongoing support.',
  },
  {
    question: 'Is there a free trial?',
    answer:
      'Join the waitlist to be among the first to try Axiom.',
  },
  {
    question: 'When will Axiom launch?',
    answer:
      "We're building the most accurate Canadian crypto tax platform. Join the waitlist and we'll notify you.",
  },
  {
    question: 'Can I use Axiom for my business?',
    answer:
      'Yes. Axiom supports both personal and business crypto tax reporting.',
  },
]

export default function PricingPage() {
  return (
    <>
      {/* Hero */}
      <SectionWrapper aria-label="Pricing overview">
        <div className="text-center max-w-2xl mx-auto">
          <h1 className="text-4xl md:text-6xl font-bold mb-6">
            <span className="gradient-text">
              One price. One tax year. No surprises.
            </span>
          </h1>
          <p className="text-base text-muted-foreground">
            Simple flat-fee annual pricing. All features included. No
            per-transaction fees, no tier upgrades, no hidden costs.
          </p>
        </div>
      </SectionWrapper>

      {/* Pricing Card */}
      <SectionWrapper aria-label="Pricing details">
        <div className="flex justify-center">
          <PricingCard />
        </div>
      </SectionWrapper>

      {/* FAQ */}
      <SectionWrapper aria-label="Frequently asked questions">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-2xl md:text-3xl font-bold mb-8 text-center">
            Frequently asked questions
          </h2>
          <div className="space-y-6">
            {faqs.map((faq) => (
              <div
                key={faq.question}
                className="border border-border rounded-lg p-6 bg-card"
              >
                <h3 className="text-lg font-semibold mb-2">{faq.question}</h3>
                <p className="text-sm text-muted-foreground">{faq.answer}</p>
              </div>
            ))}
          </div>
        </div>
      </SectionWrapper>

      {/* Bottom CTA */}
      <SectionWrapper aria-label="Get started">
        <div className="text-center max-w-xl mx-auto">
          <h2 className="text-2xl md:text-3xl font-bold mb-4">
            Ready to simplify your crypto taxes?
          </h2>
          <p className="text-base text-muted-foreground mb-8">
            Join the waitlist and be first in line when we launch.
          </p>
          <WaitlistForm variant="standalone" />
        </div>
      </SectionWrapper>
    </>
  )
}
