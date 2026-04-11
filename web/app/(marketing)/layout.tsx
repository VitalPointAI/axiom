import PlausibleProvider from 'next-plausible'
import MarketingNav from '@/components/marketing/marketing-nav'
import MarketingFooter from '@/components/marketing/marketing-footer'

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <PlausibleProvider src="https://analytics.axiom.tax/js/pa-axiom.js" init={{ endpoint: 'https://analytics.axiom.tax/api/event' }}>
      {/* Animated ambient gradient background */}
      <div
        className="fixed inset-0 pointer-events-none"
        aria-hidden="true"
        style={{
          background: [
            'radial-gradient(ellipse 800px 600px at 25% 15%, rgba(99,102,241,0.20) 0%, transparent 70%)',
            'radial-gradient(ellipse 600px 600px at 75% 55%, rgba(139,92,246,0.14) 0%, transparent 70%)',
            'radial-gradient(ellipse 500px 400px at 45% 85%, rgba(6,182,212,0.12) 0%, transparent 70%)',
          ].join(', '),
          animation: 'drift 20s ease-in-out infinite alternate',
        }}
      />
      <MarketingNav />
      <main className="relative min-h-screen">{children}</main>
      <MarketingFooter />
    </PlausibleProvider>
  )
}
