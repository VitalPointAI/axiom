import PlausibleProvider from 'next-plausible'
import MarketingNav from '@/components/marketing/marketing-nav'
import MarketingFooter from '@/components/marketing/marketing-footer'

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <PlausibleProvider domain="axiom.tax" customDomain="https://analytics.axiom.tax" selfHosted>
      <MarketingNav />
      <main className="min-h-screen">{children}</main>
      <MarketingFooter />
    </PlausibleProvider>
  )
}
