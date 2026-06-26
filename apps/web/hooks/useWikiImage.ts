import { useState, useEffect } from 'react'

const cache = new Map<string, string | null>()

/**
 * Fetches a destination photo from Wikipedia (free, no API key, CORS-safe).
 * Returns null while loading; caches results in-memory.
 */
export function useWikiImage(city: string, country = ''): string | null {
  const key = city
  const [imgUrl, setImgUrl] = useState<string | null>(() => cache.get(key) ?? null)

  useEffect(() => {
    if (cache.has(key)) { setImgUrl(cache.get(key) ?? null); return }

    const q = encodeURIComponent(`${city}${country ? ' ' + country : ''} tourism travel`)
    fetch(
      `https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch=${q}&gsrlimit=1&prop=pageimages&format=json&pithumbsize=600&origin=*`
    )
      .then(r => r.json())
      .then(d => {
        const pages = d?.query?.pages ?? {}
        const src =
          (Object.values(pages)[0] as { thumbnail?: { source: string } })?.thumbnail?.source ??
          null
        cache.set(key, src)
        setImgUrl(src)
      })
      .catch(() => { cache.set(key, null) })
  }, [key, city, country])

  return imgUrl
}
