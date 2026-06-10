import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server, READINGS_URL, defaultReadings } from './test/handlers'
import { fetchReadings } from './api'

describe('fetchReadings', () => {
  it('returns parsed readings on success', async () => {
    const result = await fetchReadings(1)
    expect(result).toHaveLength(2)
    expect(result[0].temperature_c).toBe(21)
    expect(result[0].humidity_pct).toBe(64)
    expect(result[0].timestamp).toBe(1700000000)
  })

  it('throws with status code on non-200 response', async () => {
    server.use(
      http.get(READINGS_URL, () => HttpResponse.json({}, { status: 500 }))
    )
    await expect(fetchReadings(1)).rejects.toThrow('API error 500')
  })

  it('throws on network failure', async () => {
    server.use(
      http.get(READINGS_URL, () => HttpResponse.error())
    )
    await expect(fetchReadings(1)).rejects.toThrow()
  })

  it('sends device_id as query param', async () => {
    let capturedUrl = ''
    server.use(
      http.get(READINGS_URL, ({ request }) => {
        capturedUrl = request.url
        return HttpResponse.json({ device_id: 42, readings: defaultReadings })
      })
    )
    await fetchReadings(42)
    expect(capturedUrl).toContain('device_id=42')
  })
})
