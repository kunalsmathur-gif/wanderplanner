import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ListeningOrb } from '@/components/voice/ListeningOrb'

describe('ListeningOrb', () => {
  it('shows a prominent listening status label while recording', () => {
    render(<ListeningOrb isActive isRecording />)

    expect(screen.getByText('Listening')).toBeInTheDocument()
  })

  it('includes reduced-motion fallbacks for orb animations', () => {
    const { container } = render(<ListeningOrb isActive isRecording />)
    const style = container.querySelector('style')

    expect(style?.textContent).toContain('@media (prefers-reduced-motion: reduce)')
    expect(style?.textContent).toContain('animation: none')
  })
})
