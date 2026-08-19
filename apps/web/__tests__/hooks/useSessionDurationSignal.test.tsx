import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useSessionDurationSignal } from '@/hooks/useSessionDurationSignal'
import { useItineraryStore } from '@/store/itineraryStore'
import { sendGenerationSignal } from '@/lib/api'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, sendGenerationSignal: vi.fn() }
})

const mockedSendGenerationSignal = vi.mocked(sendGenerationSignal)

function setGeneration(generationId: string | undefined, generatedAt: number | null) {
  useItineraryStore.setState({ generationId, generatedAt })
}

describe('useSessionDurationSignal', () => {
  beforeEach(() => {
    mockedSendGenerationSignal.mockClear()
    vi.useFakeTimers()
    setGeneration(undefined, null)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does nothing when there is no generationId', () => {
    const { unmount } = renderHook(() => useSessionDurationSignal())
    unmount()
    expect(mockedSendGenerationSignal).not.toHaveBeenCalled()
  })

  it('reports elapsed session duration on unmount', () => {
    const start = Date.now()
    setGeneration('gen-1', start)
    const { unmount, rerender } = renderHook(() => useSessionDurationSignal())
    rerender()

    vi.setSystemTime(start + 45_000)
    unmount()

    expect(mockedSendGenerationSignal).toHaveBeenCalledWith('gen-1', 'session_duration', 45)
  })

  it('reports the previous generation before switching to a new one', () => {
    const start = Date.now()
    setGeneration('gen-1', start)
    const { rerender, unmount } = renderHook(() => useSessionDurationSignal())

    vi.setSystemTime(start + 10_000)
    act(() => {
      setGeneration('gen-2', start + 10_000)
      rerender()
    })

    expect(mockedSendGenerationSignal).toHaveBeenCalledWith('gen-1', 'session_duration', 10)

    vi.setSystemTime(start + 30_000)
    unmount()
    expect(mockedSendGenerationSignal).toHaveBeenCalledWith('gen-2', 'session_duration', 20)
  })

  it('reports on pagehide/beforeunload without waiting for unmount', () => {
    const start = Date.now()
    setGeneration('gen-1', start)
    renderHook(() => useSessionDurationSignal())

    vi.setSystemTime(start + 5_000)
    window.dispatchEvent(new Event('pagehide'))

    expect(mockedSendGenerationSignal).toHaveBeenCalledWith('gen-1', 'session_duration', 5)
  })
})
