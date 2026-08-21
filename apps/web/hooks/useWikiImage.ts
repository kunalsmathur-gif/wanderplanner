import { useState, useEffect } from 'react'

const cache = new Map<string, string | null>()

/**
 * Fetches a destination photo from Wikipedia (free, no API key, CORS-safe).
 * Returns null while loading; caches results in-memory.
 * @param city      City name used as the default search term.
 * @param country   Optional country for disambiguation.
 * @param imageQuery Override the Wikipedia search term entirely (use when the
 *                  default city search returns a map or has no thumbnail).
 * @param thumbSize Requested thumbnail width in px (Wikipedia's `pithumbsize`).
 *                  Defaults to 600, sized for the ~130px-tall gallery cards.
 *                  Callers rendering a larger banner (e.g. a full-width hero)
 *                  should pass a bigger value — reusing 600px there stretches
 *                  a low-res image across a much larger area and looks
 *                  visibly blurry. Included in the cache key so a small
 *                  thumbnail fetched for one context never gets reused (and
 *                  look blurry) in a context asking for a larger size.
 */
export function useWikiImage(city: string, country = '', imageQuery?: string, thumbSize = 600): string | null {
  const key = `${imageQuery ?? city}::${thumbSize}`
  const [imgUrl, setImgUrl] = useState<string | null>(() => cache.get(key) ?? null)

  useEffect(() => {
    if (cache.has(key)) { setImgUrl(cache.get(key) ?? null); return }

    const q = encodeURIComponent(imageQuery ?? `${city}${country ? ' ' + country : ''} tourism travel`)
    fetch(
      `https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch=${q}&gsrlimit=1&prop=pageimages&format=json&pithumbsize=${thumbSize}&origin=*`
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
  }, [key, city, country, imageQuery, thumbSize])

  return imgUrl
}

