import Link from 'next/link'
import { Button } from '@/components/ui/button'

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4">
      <h1 className="text-4xl font-bold mb-4">404</h1>
      <p className="text-muted-foreground mb-8">
        This page doesn&apos;t exist. Head back to the homepage.
      </p>
      <Link href="/">
        <Button>Go home</Button>
      </Link>
    </div>
  )
}
