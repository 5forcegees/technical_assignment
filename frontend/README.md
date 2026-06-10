# frontend/

React + TypeScript single-page application for monitoring weather station readings. Connects to the query Lambda via API Gateway, displays the latest reading and a historical table, and polls for new data every 60 seconds.

---

## Features

- **Device selector** — enter any device ID and click Load to switch stations
- **Latest reading card** — shows the most recent temperature, humidity, and timestamp for the selected device
- **Historical table** — lists all readings returned by the query (default: last 24 hours, up to 100 readings)
- **Auto-refresh** — polls `GET /readings` every 60 seconds, matching the device sample rate
- **Error display** — surfaces API errors inline without crashing the UI

---

## Directory Layout

```
src/
  main.tsx           React entry point
  App.tsx            Root component — all UI state and data fetching
  App.css            Minimal base styles
  index.css          Global reset
  api.ts             fetchReadings() — typed API client

  test/
    setup.ts         Vitest global setup — starts the MSW server
    handlers.ts      MSW request handlers and shared test fixtures

  api.test.ts        Unit tests for the API client
  App.test.tsx       Component tests for App

public/
  favicon.svg
  icons.svg

index.html           Vite HTML entry point
vite.config.ts       Vite + Vitest configuration
tsconfig.json        TypeScript project references
.env.example         Template for required environment variables
```

---

## Configuration

The app requires one environment variable:

| Variable | Description |
|---|---|
| `VITE_API_URL` | Base URL of the API Gateway endpoint, without a trailing slash |

Copy `.env.example` to `.env` and fill in the value from the Stage2 Terraform output:

```bash
cp .env.example .env
# Edit .env:
# VITE_API_URL=https://<id>.execute-api.<region>.amazonaws.com
```

In tests, `VITE_API_URL` is set to `""` (empty string) in `vite.config.ts` so all requests use a relative path that MSW can intercept without needing a real server.

---

## API Contract

The app calls one endpoint:

```
GET /readings?device_id=<n>&limit=<n>
```

Expected response:

```json
{
  "device_id": 42,
  "readings": [
    {
      "device_id":     42,
      "timestamp":     1700000000,
      "temperature_c": 23,
      "humidity_pct":  65
    }
  ]
}
```

Readings are returned sorted oldest-to-newest. The app uses `readings.at(-1)` as the latest reading. The `fetchReadings()` function in `api.ts` throws on any non-2xx response; the `App` component catches and displays the error message.

---

## Testing

Tests use **Vitest** as the test runner and **Mock Service Worker (MSW)** to intercept fetch calls at the network layer. MSW intercepts at the network boundary rather than patching `fetch` — tests are agnostic to the HTTP client and the handler definitions can be reused for development mocking.

**`src/api.test.ts`** — unit tests for `fetchReadings()`:
- Returns parsed readings on success
- Throws with the HTTP status code on non-2xx responses
- Throws on network failure
- Sends `device_id` as a query parameter

**`src/App.test.tsx`** — component tests:
- Renders the readings table after a successful fetch
- Displays the latest reading in the summary card
- Shows an error message when the API returns a non-2xx status
- Shows the empty state when the API returns an empty readings array
- Shows "Unknown error" when a non-Error value is thrown
- Does not trigger a new fetch when the device ID input is non-numeric
- Automatically re-fetches after 60 seconds (tested with fake timers)
- Fetches from the correct device ID when Load is clicked

---

## Developer Guide

### Prerequisites

- Node.js ≥ 18
- npm ≥ 9

### Install dependencies

```bash
npm install
```

### Run the development server

```bash
npm run dev
```

Opens at `http://localhost:5173`. Requires `VITE_API_URL` to be set in `.env` to show real data. Without it, API calls will fail with a network error (expected in local dev without the stack deployed).

### Run tests

```bash
npm test
```

Runs all tests once with Vitest in run mode. No environment variables or network access required — MSW intercepts all requests.

Expected output:

```
 Test Files  2 passed (2)
      Tests  12 passed (12)
```

### Watch mode (during development)

```bash
npm run test:watch
```

Reruns affected tests on file save.

### Coverage report

```bash
npm run coverage
```

Generates a coverage report in `coverage/` and prints a summary to the terminal. Open `coverage/index.html` in a browser for a line-by-line view.

### Type check

```bash
npx tsc --noEmit
```

Runs the TypeScript compiler without emitting output. Use this to catch type errors without building.

### Lint

```bash
npm run lint
```

Runs ESLint with the React Hooks and React Refresh plugins. The config is in `eslint.config.js`.

### Production build

```bash
npm run build
```

Outputs to `dist/`. The build runs `tsc -b` (type check) before Vite bundles, so a type error will fail the build.

### Preview the production build locally

```bash
npm run preview
```

Serves the `dist/` folder at `http://localhost:4173`. Useful for verifying the production bundle before deploying.

### Deploy

The frontend is a static site. After `npm run build`, upload `dist/` to any static host (S3 + CloudFront, Vercel, Netlify, etc.). Ensure `VITE_API_URL` is set correctly at build time — it is baked into the bundle.

Example deployment to S3:

```bash
VITE_API_URL=https://<id>.execute-api.<region>.amazonaws.com \
  npm run build

aws s3 sync dist/ s3://<your-bucket>/ --delete
```
