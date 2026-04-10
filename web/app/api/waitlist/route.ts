/**
 * Next.js API route proxy for waitlist signups.
 *
 * Forwards POST requests to the FastAPI backend at /api/waitlist.
 * No authentication required -- this is a public marketing endpoint.
 *
 * The proxy approach avoids CORS issues since the frontend calls
 * same-origin /api/waitlist which is forwarded server-side.
 */

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

    const res = await fetch(`${apiUrl}/api/waitlist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: body.email }),
    })

    const data = await res.json()
    return Response.json(data, { status: res.status })
  } catch {
    return Response.json(
      {
        message:
          'Something went wrong. Please try again, or email us at hello@axiom.tax.',
      },
      { status: 500 },
    )
  }
}
