import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

export const READINGS_URL = '/readings'

// Ascending timestamp order — matches DynamoDB Query default sort
export const defaultReadings = [
  { device_id: 1, timestamp: 1700000000, temperature_c: 21, humidity_pct: 64 },
  { device_id: 1, timestamp: 1700000060, temperature_c: 22, humidity_pct: 65 },
]

export const server = setupServer(
  http.get(READINGS_URL, () =>
    HttpResponse.json({ device_id: 1, readings: defaultReadings })
  )
)
