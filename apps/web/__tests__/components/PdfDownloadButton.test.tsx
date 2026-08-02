import * as React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PdfDownloadButton } from '@/components/pdf/PdfDownloadButton'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'

const getDayPhotos = vi.fn()
vi.mock('@/lib/api', () => ({ getDayPhotos: (...args: unknown[]) => getDayPhotos(...args) }))

// Captures the days each render attempt was handed, so a test can assert what
// the retry actually fell back to.
const renderedWith: unknown[][] = []
const toBlob = vi.fn()

vi.mock('@react-pdf/renderer', () => ({
  pdf: (element: { props: { days: unknown[] } }) => {
    renderedWith.push(element.props.days)
    return { toBlob }
  },
}))
vi.mock('@/components/pdf/ItineraryDocument', () => ({
  ItineraryDocument: (props: unknown) => props,
}))

const day = (n: number, theme: string) => ({
  day_number: n,
  date: '2026-01-0' + n,
  theme,
  items: [],
})

async function clickDownload() {
  await userEvent.click(screen.getByRole('button', { name: /Download Itinerary PDF/i }))
}

describe('PdfDownloadButton — day photos are fetched at download time', () => {
  beforeEach(() => {
    renderedWith.length = 0
    getDayPhotos.mockReset()
    toBlob.mockReset().mockResolvedValue(new Blob(['pdf']))

    global.URL.createObjectURL = vi.fn(() => 'blob:pdf')
    global.URL.revokeObjectURL = vi.fn()

    useItineraryStore.getState().reset()
    useItineraryStore.getState().setDays([day(1, 'beaches'), day(2, 'forts')] as never, 80)
    useTripConfigStore.setState({
      config: { destination: { city: 'Goa', country: 'India' } },
    } as never)
  })

  it('does not fetch photos until the user asks for the PDF', () => {
    render(<PdfDownloadButton />)

    // The whole point of the move: generation no longer pays for these, and
    // neither does merely loading the dashboard.
    expect(getDayPhotos).not.toHaveBeenCalled()
  })

  it('queries "{destination} {theme}" per day, matching the old backend key', async () => {
    // services/pexels.py caches per query string — drifting from the format
    // generation used would silently double the Pexels calls for same photos.
    getDayPhotos.mockResolvedValue([
      { url: 'https://img/1.jpg', photographer: 'Ada', photographer_url: 'https://p/ada' },
      { url: 'https://img/2.jpg', photographer: 'Ada', photographer_url: 'https://p/ada' },
    ])
    render(<PdfDownloadButton />)

    await clickDownload()

    await waitFor(() => expect(getDayPhotos).toHaveBeenCalledWith(['Goa beaches', 'Goa forts']))
  })

  it('falls back to the country for the query prefix when no city is resolved', async () => {
    getDayPhotos.mockResolvedValue([])
    useTripConfigStore.setState({
      config: { destination: null, destination_country: 'India' },
    } as never)
    render(<PdfDownloadButton />)

    await clickDownload()

    await waitFor(() => expect(getDayPhotos).toHaveBeenCalledWith(['India beaches', 'India forts']))
  })

  it('attaches returned photos to the rendered document', async () => {
    getDayPhotos.mockResolvedValue([
      { url: 'https://img/1.jpg', photographer: 'Ada', photographer_url: 'https://p/ada' },
      { url: 'https://img/2.jpg', photographer: 'Bo', photographer_url: 'https://p/bo' },
    ])
    render(<PdfDownloadButton />)

    await clickDownload()

    await waitFor(() => expect(renderedWith).toHaveLength(1))
    const days = renderedWith[0] as { image_url: string; image_photographer: string }[]
    expect(days[0].image_url).toBe('https://img/1.jpg')
    expect(days[1].image_photographer).toBe('Bo')
  })

  describe('when Pexels is unavailable', () => {
    it('still produces a PDF when the photo request fails outright', async () => {
      // Pexels down, our endpoint 500ing, 429 rate limit, 401 expired session,
      // offline, or past the 6s timeout — all land here.
      getDayPhotos.mockRejectedValue(new Error('503 Service Unavailable'))
      render(<PdfDownloadButton />)

      await clickDownload()

      await waitFor(() => expect(toBlob).toHaveBeenCalled())
      expect(screen.queryByText(/Could not generate the PDF/i)).not.toBeInTheDocument()
      const days = renderedWith[0] as { image_url?: string }[]
      expect(days[0].image_url).toBeUndefined()
    })

    it('renders the days it did get photos for and skips the rest', async () => {
      getDayPhotos.mockResolvedValue([
        { url: '', photographer: '', photographer_url: '' },
        { url: 'https://img/2.jpg', photographer: 'Bo', photographer_url: 'https://p/bo' },
      ])
      render(<PdfDownloadButton />)

      await clickDownload()

      await waitFor(() => expect(toBlob).toHaveBeenCalled())
      const days = renderedWith[0] as { image_url?: string }[]
      expect(days[0].image_url).toBeUndefined()
      expect(days[1].image_url).toBe('https://img/2.jpg')
    })

    it('tolerates a short batch without misaligning days', async () => {
      getDayPhotos.mockResolvedValue([
        { url: 'https://img/1.jpg', photographer: 'Ada', photographer_url: 'https://p/ada' },
      ])
      render(<PdfDownloadButton />)

      await clickDownload()

      await waitFor(() => expect(toBlob).toHaveBeenCalled())
      const days = renderedWith[0] as { image_url?: string; theme: string }[]
      expect(days[0].image_url).toBe('https://img/1.jpg')
      expect(days[1].theme).toBe('forts')
      expect(days[1].image_url).toBeUndefined()
    })
  })

  describe('when a photo URL sinks the render', () => {
    it('retries without images rather than losing the PDF', async () => {
      // 🔴 The URL can pass the fetch and still break the download: @react-pdf
      // resolves every <Image src> over the network at render time, so a dead
      // or slow CDN URL throws out of .toBlob() and takes the document down.
      getDayPhotos.mockResolvedValue([
        { url: 'https://img/dead.jpg', photographer: 'Ada', photographer_url: 'https://p/ada' },
        { url: 'https://img/2.jpg', photographer: 'Bo', photographer_url: 'https://p/bo' },
      ])
      toBlob
        .mockRejectedValueOnce(new Error('Failed to fetch image'))
        .mockResolvedValueOnce(new Blob(['pdf']))
      render(<PdfDownloadButton />)

      await clickDownload()

      await waitFor(() => expect(toBlob).toHaveBeenCalledTimes(2))
      expect(screen.queryByText(/Could not generate the PDF/i)).not.toBeInTheDocument()

      const [first, second] = renderedWith as { image_url?: string }[][]
      expect(first[0].image_url).toBe('https://img/dead.jpg')
      expect(second[0].image_url).toBeUndefined()
    })

    it('does not retry when no photos were attached', async () => {
      // Nothing to strip, so a second attempt would fail identically and just
      // double the user's wait before the error appears.
      getDayPhotos.mockRejectedValue(new Error('offline'))
      toBlob.mockRejectedValue(new Error('renderer exploded'))
      render(<PdfDownloadButton />)

      await clickDownload()

      await waitFor(() =>
        expect(screen.getByText(/Could not generate the PDF/i)).toBeInTheDocument()
      )
      expect(toBlob).toHaveBeenCalledTimes(1)
    })

    it('surfaces the error when even the image-free retry fails', async () => {
      getDayPhotos.mockResolvedValue([
        { url: 'https://img/1.jpg', photographer: 'Ada', photographer_url: 'https://p/ada' },
        { url: 'https://img/2.jpg', photographer: 'Bo', photographer_url: 'https://p/bo' },
      ])
      toBlob.mockRejectedValue(new Error('renderer exploded'))
      render(<PdfDownloadButton />)

      await clickDownload()

      await waitFor(() =>
        expect(screen.getByText(/Could not generate the PDF/i)).toBeInTheDocument()
      )
      expect(toBlob).toHaveBeenCalledTimes(2)
    })
  })
})
