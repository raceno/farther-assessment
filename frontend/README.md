# Portfolio breakdown (Farther frontend assessment)

Vite + React + TypeScript UI for inspecting nested **client → accounts → holdings** data. Types and normalization mirror the partner JSON shape and the backend `GET /clients/{client_id}` response.

## Setup

```bash
npm install
```

## Run locally

```bash
npm run dev
```

Open the URL shown (typically `http://localhost:5173`). Font size defaults to 16px+ for screen sharing.

## Connect to the backend API

1. Start the FastAPI service from the repo root’s `backend/` folder (see that `README.md`).
2. Copy `.env.example` to `.env` in this folder:

   ```bash
   copy .env.example .env
   ```

   Set `VITE_API_BASE_URL=http://localhost:8000` (no trailing slash).

3. Ingest sample data once (e.g. run `python test_local.py` from `backend/` while the server is up).
4. In the UI, enable **Fetch from API** and load a client id that exists in the database (e.g. `CLT-29481`).

Without `.env`, the app uses bundled [`src/data/sample-portfolio.json`](src/data/sample-portfolio.json`) so the table works offline.

## Behavior

- **Client ID** + **Load** updates the data source; `clientId` and `account` are reflected in the URL query string for deep linking.
- **Account tabs** switch holdings; selection updates `?account=…`.
- **Normalization warnings** appear when the payload shape drifts (coercion / missing arrays).
- **Edge cases**: empty accounts list; empty holdings with cash/total still shown; API errors with a clear banner.

## Scripts

| Command        | Purpose                |
|----------------|------------------------|
| `npm run dev`  | Dev server with HMR    |
| `npm run build`| Production build       |
| `npm run preview` | Preview production build |
| `npm run lint` | ESLint                 |
