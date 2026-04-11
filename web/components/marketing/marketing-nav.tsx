'use client'

import { useState, useEffect } from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { Menu, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import ThemeToggle from '@/components/marketing/theme-toggle'

const navLinks = [
  { href: '/features', label: 'Features' },
  { href: '/pricing', label: 'Pricing' },
  { href: '/privacy', label: 'Privacy' },
  { href: '/compliance', label: 'Compliance' },
  { href: '/about', label: 'About' },
]

export default function MarketingNav() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 10)
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  return (
    <nav
      className={`fixed top-0 w-full z-50 h-16 transition-all duration-300 ease-out ${
        scrolled
          ? 'bg-background/90 backdrop-blur-md border-b border-border'
          : 'bg-transparent'
      }`}
    >
      <div className="max-w-[1200px] mx-auto px-4 md:px-6 lg:px-8 h-full flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 font-bold text-xl text-foreground">
          <Image src="/axiom-logomark.svg" alt="" width={28} height={28} className="h-7 w-7" />
          Axiom
        </Link>

        {/* Desktop nav links */}
        <div className="hidden lg:flex items-center gap-6">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </div>

        {/* Right side: theme toggle + CTA */}
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link href="/#waitlist" className="hidden sm:block">
            <Button>Join the waitlist</Button>
          </Link>

          {/* Mobile hamburger */}
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden min-h-[44px] min-w-[44px]"
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
        </div>
      </div>

      {/* Mobile dropdown */}
      {mobileOpen && (
        <div className="lg:hidden bg-background/95 backdrop-blur-md border-b border-border">
          <div className="max-w-[1200px] mx-auto px-4 py-4 flex flex-col gap-2">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors py-2 min-h-[44px] flex items-center"
                onClick={() => setMobileOpen(false)}
              >
                {link.label}
              </Link>
            ))}
            <Link href="/#waitlist" onClick={() => setMobileOpen(false)}>
              <Button className="w-full mt-2 min-h-[44px]">Join the waitlist</Button>
            </Link>
          </div>
        </div>
      )}
    </nav>
  )
}
