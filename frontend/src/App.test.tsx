import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server, READINGS_URL, defaultReadings } from './test/handlers'
import App from './App'
import * as api from './api'

describe('App', () => {
  it('renders readings table after successful fetch', async () => {
    render(<App />)
    await waitFor(() =>
      expect(screen.getByText('Last 2 readings')).toBeInTheDocument()
    )
    expect(screen.getAllByRole('row')).toHaveLength(3) // header + 2 data rows
  })

  it('displays latest reading in summary card', async () => {
    render(<App />)
    await waitFor(() =>
      expect(screen.getByText(/Latest/)).toBeInTheDocument()
    )
    expect(screen.getByText(/22 °C/)).toBeInTheDocument()
    expect(screen.getByText(/65 %/)).toBeInTheDocument()
  })

  it('shows error message when API fails', async () => {
    server.use(
      http.get(READINGS_URL, () => HttpResponse.json({}, { status: 503 }))
    )
    render(<App />)
    await waitFor(() =>
      expect(screen.getByText(/API error 503/)).toBeInTheDocument()
    )
  })

  it('shows empty state when no readings returned', async () => {
    server.use(
      http.get(READINGS_URL, () =>
        HttpResponse.json({ device_id: 1, readings: [] })
      )
    )
    render(<App />)
    await waitFor(() =>
      expect(screen.getByText(/No readings found/)).toBeInTheDocument()
    )
  })

  it('shows "Unknown error" when a non-Error value is thrown', async () => {
    vi.spyOn(api, 'fetchReadings').mockRejectedValueOnce('plain string, not an Error')
    render(<App />)
    await waitFor(() =>
      expect(screen.getByText(/Unknown error/)).toBeInTheDocument()
    )
    vi.restoreAllMocks()
  })

  it('does not trigger a load when device ID input is non-numeric', async () => {
    const user = userEvent.setup()
    const urls: string[] = []
    server.use(
      http.get(READINGS_URL, ({ request }) => {
        urls.push(request.url)
        return HttpResponse.json({ device_id: 1, readings: defaultReadings })
      })
    )
    render(<App />)
    await waitFor(() => screen.getByText('Last 2 readings'))

    const countBefore = urls.length
    await user.clear(screen.getByLabelText(/Device ID/i))
    await user.type(screen.getByLabelText(/Device ID/i), 'notanumber')
    await user.click(screen.getByRole('button', { name: /Load/i }))

    // No new fetch — deviceId was not updated
    await new Promise(resolve => setTimeout(resolve, 100))
    expect(urls.length).toBe(countBefore)
  })

  it('automatically re-fetches after POLL_INTERVAL_MS', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let callCount = 0
    server.use(
      http.get(READINGS_URL, () => {
        callCount++
        return HttpResponse.json({ device_id: 1, readings: defaultReadings })
      })
    )
    render(<App />)
    await waitFor(() => expect(callCount).toBeGreaterThanOrEqual(1))

    vi.advanceTimersByTime(60_001)
    await waitFor(() => expect(callCount).toBeGreaterThanOrEqual(2))

    vi.useRealTimers()
  })

  it('fetches new device when Load is clicked', async () => {
    const user = userEvent.setup()
    let lastUrl = ''
    server.use(
      http.get(READINGS_URL, ({ request }) => {
        lastUrl = request.url
        return HttpResponse.json({ device_id: 99, readings: defaultReadings })
      })
    )
    render(<App />)
    await waitFor(() => screen.getByText('Last 2 readings'))

    await user.clear(screen.getByLabelText(/Device ID/i))
    await user.type(screen.getByLabelText(/Device ID/i), '99')
    await user.click(screen.getByRole('button', { name: /Load/i }))

    await waitFor(() => expect(lastUrl).toContain('device_id=99'))
  })
})
