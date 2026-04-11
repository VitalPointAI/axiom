import type { Metadata } from 'next'
import SectionWrapper from '@/components/marketing/section-wrapper'
import WaitlistForm from '@/components/marketing/waitlist-form'
import {
  Lock,
  Cpu,
  KeyRound,
  Globe,
  Repeat,
  Layers,
  Mail,
} from 'lucide-react'

export const metadata: Metadata = {
  title: 'About - Axiom',
  description:
    'Building the first Canadian-sovereign, blockchain-native crypto tax platform.',
  openGraph: {
    title: 'About - Axiom',
    description:
      'Building the first Canadian-sovereign, blockchain-native crypto tax platform.',
    type: 'website',
    locale: 'en_CA',
  },
  twitter: { card: 'summary_large_image' },
}

const roadmapItems = [
  {
    icon: Lock,
    title: 'Post-Quantum Encryption',
    description:
      'AES-256 encryption with planned quantum-resistant key exchange to future-proof your data.',
  },
  {
    icon: Cpu,
    title: 'Zero-Knowledge Tax Calculations',
    description:
      'Client-side computation so your raw transaction data never reaches our servers.',
  },
  {
    icon: KeyRound,
    title: 'Passkey-Derived Encryption',
    description:
      'Your hardware security key derives the encryption key for your data. Even we cannot access it.',
  },
  {
    icon: Globe,
    title: 'Multi-Chain Expansion',
    description:
      'Solana, Bitcoin, Cosmos ecosystem, Avalanche, Arbitrum, and any chain our users need.',
  },
  {
    icon: Repeat,
    title: 'Exchange API Sync',
    description:
      'Direct API connections to Coinbase, Crypto.com, Bitbuy, and other Canadian exchanges.',
  },
  {
    icon: Layers,
    title: 'DeFi Protocol Support',
    description:
      'Deep integration with lending protocols, liquidity pools, yield aggregators, and NFT marketplaces.',
  },
]

export default function AboutPage() {
  return (
    <>
      {/* Mission Statement */}
      <SectionWrapper aria-label="Our mission">
        <h1 className="text-4xl md:text-6xl font-bold mb-8">
          <span className="gradient-text">
            Crypto taxes, done right.
          </span>
        </h1>
        <div className="max-w-3xl space-y-6">
          <p className="text-base text-muted-foreground">
            We believe Canadians deserve a crypto tax platform that&apos;s
            accurate, private, and built for Canadian tax law. Not adapted from a
            US product. Not a spreadsheet with a UI. A purpose-built tool that
            reads the blockchain, understands CRA rules, and keeps your data in
            Canada.
          </p>
          <p className="text-base text-muted-foreground">
            Axiom was born from frustration. We tried every crypto tax tool on
            the market and found the same problems: missing transactions, wrong
            cost basis calculations, data shipped to foreign servers, and no
            understanding of Canadian-specific rules like superficial loss with
            proration.
          </p>
          <p className="text-base text-muted-foreground">
            So we built something better. Axiom reads the blockchain directly
            for on-chain transactions, with CSV import for exchange data. It calculates ACB the way the CRA
            requires. It keeps every byte of your data in Toronto. And it&apos;s
            built to be the most accurate crypto tax platform in Canada.
          </p>
        </div>
      </SectionWrapper>

      {/* Team */}
      <SectionWrapper aria-label="Our team">
        <h2 className="text-2xl md:text-3xl font-bold mb-4">Who we are</h2>
        <p className="text-base text-muted-foreground max-w-2xl">
          Built by crypto holders who got tired of broken tax tools. We&apos;ve
          dealt with missing transactions, incorrect cost basis calculations, and
          platforms that don&apos;t understand Canadian tax law. Axiom is the
          tool we wished existed.
        </p>
      </SectionWrapper>

      {/* Future Roadmap */}
      <SectionWrapper aria-label="Product roadmap">
        <h2 className="text-2xl md:text-3xl font-bold mb-4">
          What we&apos;re building next
        </h2>
        <p className="text-base text-muted-foreground max-w-2xl mb-8">
          Axiom is just getting started. Here&apos;s where we&apos;re headed.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {roadmapItems.map((item) => (
            <div
              key={item.title}
              className="border border-border rounded-lg p-6 bg-card hover:border-indigo-500/30 transition-colors"
            >
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center mb-4">
                <item.icon className="w-5 h-5 text-indigo-400" />
              </div>
              <h3 className="text-lg font-semibold mb-2">{item.title}</h3>
              <p className="text-sm text-muted-foreground">
                {item.description}
              </p>
            </div>
          ))}
        </div>
      </SectionWrapper>

      {/* Contact */}
      <SectionWrapper aria-label="Contact us">
        <div className="border border-border rounded-lg p-8 bg-card max-w-xl">
          <div className="flex items-center gap-3 mb-4">
            <Mail className="w-5 h-5 text-indigo-400" />
            <h2 className="text-2xl md:text-3xl font-bold">Get in touch</h2>
          </div>
          <p className="text-base text-muted-foreground mb-4">
            Questions, partnerships, or just want to say hi? We&apos;d love to
            hear from you.
          </p>
          <a
            href="mailto:hello@axiom.tax"
            className="inline-flex items-center gap-2 text-indigo-400 hover:text-indigo-300 transition-colors font-medium"
          >
            hello@axiom.tax
          </a>
        </div>
      </SectionWrapper>

      {/* Bottom CTA */}
      <SectionWrapper aria-label="Get started">
        <div className="text-center max-w-xl mx-auto">
          <h2 className="text-2xl md:text-3xl font-bold mb-4">
            Join us on the journey
          </h2>
          <p className="text-base text-muted-foreground mb-8">
            Sign up for the waitlist and be the first to know when Axiom
            launches.
          </p>
          <WaitlistForm variant="standalone" />
        </div>
      </SectionWrapper>
    </>
  )
}
