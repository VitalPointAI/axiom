import PlausibleProvider from 'next-plausible'
import MarketingNav from '@/components/marketing/marketing-nav'
import MarketingFooter from '@/components/marketing/marketing-footer'

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <PlausibleProvider src="https://analytics.axiom.tax/js/pa-axiom.js" init={{ endpoint: 'https://analytics.axiom.tax/api/event' }}>
      <div className="marketing-bg-wrap">
        <MarketingNav />
        <main className="min-h-screen">{children}</main>
        <MarketingFooter />
      </div>
    </PlausibleProvider>
  )
}
