'use client'

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { usePlausible } from 'next-plausible'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const waitlistSchema = z.object({
  email: z.string().email('Please enter a valid email address.'),
})

type WaitlistInput = z.infer<typeof waitlistSchema>

interface WaitlistFormProps {
  variant?: 'inline' | 'standalone'
}

export default function WaitlistForm({ variant = 'inline' }: WaitlistFormProps) {
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'duplicate' | 'error'>('idle')
  const plausible = usePlausible()

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<WaitlistInput>({
    resolver: zodResolver(waitlistSchema),
  })

  const onSubmit = async (data: WaitlistInput) => {
    setStatus('submitting')
    try {
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: data.email }),
      })

      const json = await res.json()

      if (res.status === 201) {
        setStatus('success')
        try { plausible('waitlist_signup') } catch {}
      } else if (res.status === 200 && json.already_registered) {
        setStatus('duplicate')
      } else {
        setStatus('error')
      }
    } catch {
      setStatus('error')
    }
  }

  if (status === 'success') {
    return (
      <p className="text-green-500 text-sm font-medium">
        You&apos;re on the list. We&apos;ll email you when Axiom opens.
      </p>
    )
  }

  if (status === 'duplicate') {
    return (
      <p className="text-blue-500 text-sm font-medium">
        You&apos;re already on the list. We&apos;ll be in touch.
      </p>
    )
  }

  if (status === 'error') {
    return (
      <p className="text-red-500 text-sm font-medium">
        Something went wrong. Please try again, or email us at hello@axiom.tax.
      </p>
    )
  }

  const isInline = variant === 'inline'

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className={isInline ? 'flex flex-row gap-2 items-start' : 'flex flex-col gap-3'}
      noValidate
    >
      <div className={isInline ? 'flex-1' : 'w-full'}>
        <Input
          type="email"
          placeholder="your@email.com"
          className="min-h-[44px]"
          aria-label="Email address"
          {...register('email')}
        />
        {errors.email && (
          <p className="text-red-500 text-xs mt-1">{errors.email.message}</p>
        )}
      </div>
      <Button
        type="submit"
        disabled={status === 'submitting'}
        className="bg-indigo-500 hover:bg-indigo-600 text-white min-h-[44px]"
      >
        {status === 'submitting' ? 'Joining...' : 'Join the waitlist'}
      </Button>
    </form>
  )
}
