import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ErrorState } from '@/components/common/ErrorState'

describe('ErrorState', () => {
  const onRetry = vi.fn()
  const onBack = vi.fn()

  it('renders default title for unknown error code', () => {
    render(<ErrorState code="UNKNOWN" onRetry={onRetry} onBack={onBack} />)
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('renders correct title for LLM_TIMEOUT', () => {
    render(<ErrorState code="LLM_TIMEOUT" onRetry={onRetry} onBack={onBack} />)
    expect(screen.getByText('Generation timed out')).toBeInTheDocument()
  })

  it('renders correct title for NETWORK_ERROR', () => {
    render(<ErrorState code="NETWORK_ERROR" onRetry={onRetry} onBack={onBack} />)
    expect(screen.getByText('Connection lost')).toBeInTheDocument()
  })

  it('renders correct title for NO_RESULTS', () => {
    render(<ErrorState code="NO_RESULTS" onRetry={onRetry} onBack={onBack} />)
    expect(screen.getByText('No results found')).toBeInTheDocument()
  })

  it('shows custom message when provided', () => {
    render(<ErrorState code="LLM_TIMEOUT" message="Custom error message" onRetry={onRetry} onBack={onBack} />)
    expect(screen.getByText('Custom error message')).toBeInTheDocument()
  })

  it('shows the error code in the UI', () => {
    render(<ErrorState code="LLM_TIMEOUT" onRetry={onRetry} onBack={onBack} />)
    expect(screen.getByText(/Error code: LLM_TIMEOUT/)).toBeInTheDocument()
  })

  it('calls onRetry when Try again is clicked', () => {
    const retry = vi.fn()
    render(<ErrorState code="LLM_TIMEOUT" onRetry={retry} onBack={onBack} />)
    fireEvent.click(screen.getByText('Try again'))
    expect(retry).toHaveBeenCalledOnce()
  })

  it('calls onBack when Edit inputs is clicked', () => {
    const back = vi.fn()
    render(<ErrorState code="LLM_TIMEOUT" onRetry={onRetry} onBack={back} />)
    fireEvent.click(screen.getByText('← Edit inputs'))
    expect(back).toHaveBeenCalledOnce()
  })
})
