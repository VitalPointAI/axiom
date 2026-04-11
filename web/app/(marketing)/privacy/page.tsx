import type { Metadata } from 'next'
import SectionWrapper from '@/components/marketing/section-wrapper'
import BreachTimeline from '@/components/marketing/breach-timeline'
import DataFlowDiagram from '@/components/marketing/data-flow-diagram'
import WaitlistForm from '@/components/marketing/waitlist-form'
import { MapPin, EyeOff, ShieldCheck, Lock, KeyRound, Cpu } from 'lucide-react'

export const metadata: Metadata = {
  title: 'Privacy & Security - Axiom',
  description:
    'Your crypto tax data stays in Canada. See our data flow, breach timeline, and security architecture.',
  openGraph: {
    title: 'Privacy & Security - Axiom',
    description:
      'Your crypto tax data stays in Canada. See our data flow, breach timeline, and security architecture.',
    type: 'website',
    locale: 'en_CA',
  },
  twitter: { card: 'summary_large_image' },
}

const sovereigntyFeatures = [
  {
    icon: MapPin,
    title: 'Toronto-Hosted Infrastructure',
    description:
      'All data is processed and stored on servers in Toronto, Canada. Your financial data never crosses international borders.',
  },
  {
    icon: EyeOff,
    title: 'No Third-Party Analytics',
    description:
      'We use Plausible (self-hosted, cookieless) for basic site analytics. No Google Analytics, no Mixpanel, no Hotjar. Your browsing is not tracked.',
  },
  {
    icon: ShieldCheck,
    title: 'PIPEDA Compliant',
    description:
      "PIPEDA (Personal Information Protection and Electronic Documents Act) is Canada's federal privacy law. Axiom is designed for PIPEDA compliance from day one.",
  },
]

const encryptionFeatures = [
  {
    icon: Lock,
    title: 'Post-Quantum Encryption',
    description:
      'AES-256 encryption with quantum-resistant key exchange protects your data against both current and future threats to cryptographic security.',
  },
  {
    icon: Cpu,
    title: 'Client-Side Zero-Knowledge Computation',
    description:
      'Your raw transaction data is processed entirely in your browser. The server only sees encrypted, aggregated results. Your financial details never reach our servers.',
  },
  {
    icon: KeyRound,
    title: 'Passkey-Derived Encryption Keys',
    description:
      'Your hardware security key (YubiKey, Touch ID, Windows Hello) derives the encryption key for your data. Even Axiom cannot access your information without your physical key.',
  },
]

export default function PrivacyPage() {
  return (
    <>
      {/* Hero */}
      <SectionWrapper aria-label="Privacy overview">
        <div className="flex flex-col md:flex-row items-center gap-8 md:gap-16">
          <div className="max-w-xl">
            <h1 className="text-4xl md:text-6xl font-bold mb-6">
              <span className="gradient-text">Your data never leaves Canada.</span>
            </h1>
            <p className="text-base text-muted-foreground">
              Axiom is built on a simple principle: your financial data belongs to
              you, and it should stay where you are. Every byte is processed and
              stored in Toronto.
            </p>
          </div>
          <div className="shrink-0">
            <img
              src="/illustrations/canada-maple.svg"
              alt="Canadian data sovereignty with Toronto-hosted servers"
              width={240}
              height={224}
              className="w-48 md:w-60 h-auto"
            />
          </div>
        </div>
      </SectionWrapper>

      {/* Breach Timeline */}
      <SectionWrapper aria-label="Breach timeline">
        <BreachTimeline />
      </SectionWrapper>

      {/* Data Flow Diagram */}
      <SectionWrapper aria-label="Data flow architecture">
        <DataFlowDiagram />
      </SectionWrapper>

      {/* Canadian Data Sovereignty */}
      <SectionWrapper aria-label="Canadian data sovereignty">
        <h2 className="text-2xl md:text-3xl font-bold mb-8">
          Canadian data sovereignty
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {sovereigntyFeatures.map((feature) => (
            <div
              key={feature.title}
              className="border border-border rounded-lg p-6 bg-card"
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

      {/* Encryption & Privacy Architecture */}
      <SectionWrapper aria-label="Encryption architecture">
        <h2 className="text-2xl md:text-3xl font-bold mb-4">
          Privacy by design, not by promise
        </h2>
        <p className="text-base text-muted-foreground mb-8 max-w-2xl">
          Axiom is architected so that even we cannot access your data.
          Post-quantum encryption, zero-knowledge computation, and
          hardware-key-derived encryption are built in from day one.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {encryptionFeatures.map((item) => (
            <div
              key={item.title}
              className="border border-emerald-500/20 rounded-lg p-6 bg-emerald-500/5"
            >
              <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center mb-4">
                <item.icon className="w-5 h-5 text-emerald-400" />
              </div>
              <h3 className="text-lg font-semibold mb-2">{item.title}</h3>
              <p className="text-sm text-muted-foreground">
                {item.description}
              </p>
            </div>
          ))}
        </div>
      </SectionWrapper>

      {/* Bottom CTA */}
      <SectionWrapper aria-label="Get started">
        <div className="text-center max-w-xl mx-auto">
          <h2 className="text-2xl md:text-3xl font-bold mb-4">
            Privacy-first crypto taxes
          </h2>
          <p className="text-base text-muted-foreground mb-8">
            Join the waitlist for Canadian-sovereign crypto tax
            reporting.
          </p>
          <WaitlistForm variant="standalone" />
        </div>
      </SectionWrapper>
    </>
  )
}
