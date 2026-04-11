import PlausibleProvider from 'next-plausible'
import MarketingNav from '@/components/marketing/marketing-nav'
import MarketingFooter from '@/components/marketing/marketing-footer'
import AnimatedBg from '@/components/marketing/animated-bg'

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <PlausibleProvider src="https://analytics.axiom.tax/js/pa-axiom.js" init={{ endpoint: 'https://analytics.axiom.tax/api/event' }}>
      <AnimatedBg />
      <MarketingNav />
      <main className="relative min-h-screen pt-16">{children}</main>
      <MarketingFooter />
    </PlausibleProvider>
  )
}
