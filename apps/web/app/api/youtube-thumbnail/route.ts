import { type NextRequest } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get('q')
  if (!q) return Response.json({ videoId: null, thumbnailUrl: null })

  try {
    const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}&sp=CAMSAhAB`
    const response = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; WanderPlan/1.0)' },
      signal: AbortSignal.timeout(5000),
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
