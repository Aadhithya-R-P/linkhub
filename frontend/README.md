# LinkHub frontend

Minimal React + Vite frontend with registration, login, session restoration, and logout. Link management is the next chunk.

## Local development (PowerShell)

Start the backend in a terminal:

```powershell
cd D:\Projects\LinkHub\backend
.\.venv\Scripts\python.exe -m fastapi dev app/main.py
```

Start the frontend in another terminal:

```powershell
cd D:\Projects\LinkHub\frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Node 22.12+ is supported by this setup.
`npm ci` installs the exact locked dependencies; it is only needed after checkout or dependency changes.

The browser posts JSON to `/api/auth/register` on the frontend origin. Vite's development proxy forwards `/api` to http://127.0.0.1:8000. This avoids a cross-origin browser request during development. It does not configure production routing or backend CORS.

The proxy preserves browser Origin headers. Backend defaults and `.env.example` include http://127.0.0.1:5173 and http://localhost:5173 in `AUTH_ALLOWED_ORIGINS`. An existing `.env` override must include the frontend origin too. This remains separate from CORS. Use one hostname consistently: localhost and 127.0.0.1 have separate cookies. Production must use its exact trusted origins and HTTPS cookie settings.

## Session flow

`AuthClient` is a class. Its constructor initializes the access token, pending operations, and session version as instance fields. The app imports one shared `auth = new AuthClient()` instance; tests construct separate instances with fake request functions. Call methods through the instance (`auth.login(...)`) so JavaScript's `this` refers to the client. For callbacks, use a wrapper such as `() => auth.logout()` rather than passing an unbound method. Fields and helper methods are ordinary public JavaScript members; components should use the client methods rather than editing fields.

`src/auth.js` keeps the access token in memory only. Login posts credentials, then requests `/api/auth/me` with the bearer token. The browser manages the HttpOnly refresh cookie; JavaScript never reads it. On startup, `restore()` refreshes the token, then calls `getCurrentUser()`. Overlapping startup calls share the pending refresh but each fetches `/me`; this allows duplicate read requests during React StrictMode effect replay without an extra restoration coordinator.

Protected requests use `apiFetch`: on a 401 they share a pending refresh, then retry once. A late 401 from an older token uses an already-replaced access token. Request bodies must be replayable (for example, JSON strings, not consumed streams). No automatic retry follows network errors because token rotation may already have happened on the server.

Logout immediately discards the local access token, waits for an in-flight refresh to finish receiving its cookie, and then posts logout. A generation counter stops an old request from restoring credentials or retrying after logout. If server logout fails, the account UI is cleared and a retry is offered; the browser cookie may still restore a session on reload.

Refresh coordination is limited to one tab. Multiple tabs share the cookie but not this in-memory coordinator, so simultaneous refreshes in different tabs can still race under the backend's accepted rotation design. Cross-tab coordination is not implemented.

## Checks

From this directory:

```powershell
npm test
npm run build
```

Tests exercise registration, login/logout UI, startup restoration, errors, concurrent refresh, late 401s, bounded retries, and logout during rotation with mocked HTTP responses. The build writes static assets to `dist/`. Deployment needs its own API routing configuration.

For manual integration testing, run both servers and create a disposable account. Expect success, then reload and submit the same email to check the duplicate error. Actual successful registrations persist in PostgreSQL. Passwords are not saved in browser storage or logged; the form clears on success.
