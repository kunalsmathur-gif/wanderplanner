import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ComparisonGrid } from '@/components/comparison/ComparisonGrid'
import type { ComparisonResponse, DestinationInput } from '@/types'

const DEST_A: DestinationInput = { city: 'Tokyo', country: 'JP', lat: 35.6, lon: 139.6 }
const DEST_B: DestinationInput = { city: 'Paris', country: 'FR', lat: 48.8, lon: 2.3 }

function makeResult(overrides?: Partial<ComparisonResponse>): ComparisonResponse {
  return {
    comparison: [
      { parameter: 'Weather', unit: '°C', values: { Tokyo: 22, Paris: 18 }, winner: 'Tokyo', highlight: '' },
      { parameter: 'Budget', unit: 'USD/day', values: { Tokyo: 120, Paris: 95 }, winner: 'Paris', highlight: '' },
      { parameter: 'Safety', unit: '', values: { Tokyo: 'High', Paris: 'Medium' }, winner: 'Tokyo', highlight: '' },
      { parameter: 'Crowds', unit: '', values: { Tokyo: 'Busy', Paris: 'Busy' }, winner: '', highlight: '' },
    ],
    partial_failures: [],
    ...overrides,
  }
}

describe('ComparisonGrid', () => {
  it('renders a row for each comparison parameter', () => {
    render(<ComparisonGrid result={makeResult()} destA={DEST_A} destB={DEST_B} />)
    expect(screen.getByText('Weather')).toBeInTheDocument()
    expect(screen.getByText('Budget')).toBeInTheDocument()
    expect(screen.getByText('Safety')).toBeInTheDocument()
    expect(screen.getByText('Crowds')).toBeInTheDocument()
  })

  it('renders destination column headers', () => {
    render(<ComparisonGrid result={makeResult()} destA={DEST_A} destB={DEST_B} />)
    // Use getAllByText since city names appear in both header and winner badges
    expect(screen.getAllByText('Tokyo').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Paris').length).toBeGreaterThanOrEqual(1)
    // Confirm column headers specifically
    expect(screen.getByRole('columnheader', { name: /Tokyo/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Paris/i })).toBeInTheDocument()
  })

  it('shows winner badges for rows with a winner', () => {
    render(<ComparisonGrid result={makeResult()} destA={DEST_A} destB={DEST_B} />)
    const winnerBadges = screen.getAllByText('Tokyo')
    // one in header + two in winner column
    expect(winnerBadges.length).toBeGreaterThanOrEqual(2)
  })

  it('shows Tie for a row with no winner', () => {
    render(<ComparisonGrid result={makeResult()} destA={DEST_A} destB={DEST_B} />)
    expect(screen.getByText('Tie')).toBeInTheDocument()
  })

  it('shows partial warning banner when partial_failures is non-empty', () => {
    render(
      <ComparisonGrid
        result={makeResult({ partial_failures: ['visa', 'currency'] })}
        destA={DEST_A}
        destB={DEST_B}
      />
    )
    expect(screen.getByText(/Partial data/)).toBeInTheDocument()
    expect(screen.getByText(/visa/)).toBeInTheDocument()
  })

  it('does NOT show warning banner when partial_failures is empty', () => {
    render(<ComparisonGrid result={makeResult()} destA={DEST_A} destB={DEST_B} />)
    expect(screen.queryByText(/Partial data/)).not.toBeInTheDocument()
  })

  it('shows insight callout after results', () => {
    render(<ComparisonGrid result={makeResult()} destA={DEST_A} destB={DEST_B} />)
    // Tokyo wins 2 rows; insight should mention Tokyo
    expect(screen.getByText(/Tokyo wins 2 of 4 parameters/)).toBeInTheDocument()
  })

  it('shows fallback insight when no winner', () => {
    render(
      <ComparisonGrid
        result={makeResult({ comparison: [{ parameter: 'X', unit: '', values: {}, winner: '', highlight: '' }] })}
        destA={DEST_A}
        destB={DEST_B}
      />
    )
    expect(screen.getByText(/comparable/)).toBeInTheDocument()
  })
})
