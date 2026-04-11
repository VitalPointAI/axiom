import Image from 'next/image'
import Link from 'next/link'

const quickLinks = [
  { href: '/features', label: 'Features' },
  { href: '/pricing', label: 'Pricing' },
  { href: '/privacy', label: 'Privacy' },
  { href: '/compliance', label: 'Compliance' },
  { href: '/about', label: 'About' },
]

export default function MarketingFooter() {
  return (
    <footer className="border-t border-border">
      <div className="max-w-[1200px] mx-auto px-4 md:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* Brand column */}
          <div>
            <div className="flex items-center gap-2">
              <Image src="/axiom-logomark.svg" alt="" width={24} height={24} className="h-6 w-6" />
              <h3 className="font-bold text-xl text-foreground">Axiom</h3>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Canadian crypto taxes, done right.
            </p>
          </div>

          {/* Quick links column */}
          <div>
            <h4 className="font-bold text-sm text-foreground mb-3">Quick Links</h4>
            <ul className="space-y-2">
              {quickLinks.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* CTA + contact column */}
          <div>
            <h4 className="font-bold text-sm text-foreground mb-3">Get Started</h4>
            <Link
              href="/#waitlist"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Join the waitlist
            </Link>
            <p className="mt-4 text-sm text-muted-foreground">
              <a
                href="mailto:hello@axiom.tax"
                className="hover:text-foreground transition-colors"
              >
                hello@axiom.tax
              </a>
            </p>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="border-t border-border mt-8 pt-8 text-center">
          <p className="text-sm text-muted-foreground">
            2026 Axiom. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  )
}
