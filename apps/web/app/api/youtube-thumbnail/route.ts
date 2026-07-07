import { type NextRequest } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get('q')
  if (!q) return Response.json({ videoId: null, thumbnailUrl: null })

  try {
    // gl/hl pin the request to the US/English result set and avoid the
    // GDPR consent-page redirect (a page with no embedded videoId at all)
    // that YouTube sometimes serves to server-side requests with no cookies.
    const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}&sp=CAMSAhAB&gl=US&hl=en&persist_gl=1`
    const response = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; WanderPlanner/1.0)',
        'Accept-Language': 'en-US,en;q=0.9',
        // Pre-accepting the EU consent cookie skips the consent interstitial
        // for requests that would otherwise be routed through it.
        Cookie: 'CONSENT=YES+cb; SOCS=CAI',
      },
      signal: AbortSignal.timeout(6000),
    })
    const html = await response.text()
    const match = html.match(/"videoId":"([a-zA-Z0-9_-]{11})"/)
    const videoId = match?.[1] ?? null
    const thumbnailUrl = videoId ? `https://img.youtube.com/vi/${videoId}/mqdefault.jpg` : null
    return Response.json({ videoId, thumbnailUrl })
  } catch {
    return Response.json({ videoId: null, thumbnailUrl: null })
  }
}
