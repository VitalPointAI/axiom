import MarketingNav from '@/components/marketing/marketing-nav'
import MarketingFooter from '@/components/marketing/marketing-footer'

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <MarketingNav />
      <main className="min-h-screen">{children}</main>
      <MarketingFooter />
    </>
  )
}
