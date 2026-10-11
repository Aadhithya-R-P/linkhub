# Link mutation rate limiting

The initial implementation deliberately limits authenticated link mutations only.
Registration, login, refresh, logout, listing, and public redirects are not limited.
IP-based authentication limits were deferred to keep the existing Vercel rewrite
and avoid adding a signed proxy or trusting caller-controlled forwarded headers.
This is not login brute-force protection or a general abuse-prevention system.

## Policy

- Each user gets 60 attempts per 60-second window, shared across POST, PATCH and
  DELETE under `/api/links` and across their sessions/devices/backend instances.
- The first counted request starts the window. Requests reaching the dependency
  after successful authentication consume budget, even if ownership/validation or
  a later database operation fails. Malformed JSON rejected before dependencies
  execute does not consume budget. Requests without valid authentication do not
  consume another user's budget.
- A rejected request receives JSON HTTP 429, `Retry-After` in whole seconds rounded
  up, and `Cache-Control: no-store`. No link mutation is executed.
- Redis failures allow mutations to continue and emit a generic warning without
  user IDs, credentials or connection details. This availability-first policy
  means the limit is temporarily unenforced during an outage.
- The window is fixed, not sliding: bursts can occur around its boundary. It does
  not provide a strict maximum over every arbitrary rolling 60-second interval.

## Implementation

`backend/app/rate_limit.py` uses one Redis Lua script for checking/incrementing the
counter and setting its TTL atomically. Blocked requests never extend the TTL.
The counter stops increasing at the limit. Expiry uses Redis time rather than
individual worker clocks. All workers must share the Redis database and JWT key.

Keys use `linkhub:limit:v1:` separately from redirect cache entries. The user ID is
HMAC-hashed with the existing backend JWT secret, using an identity prefixed with
`user:`. No IP headers are read, and no new secret or proxy configuration is needed.
Policy values are included in keys; changing the policy or JWT secret starts new
budgets while old keys expire. A missing/evicted key also starts a new budget.
Keep Upstash eviction disabled if sharing this database with limiter state.

The frontend uses `Retry-After` to block further mutation requests in the current
tab until the deadline, with a clear message. It does not queue or automatically
retry requests. Existing create/edit forms keep entered values on failure. Read
requests and logout remain available. The in-memory deadline is a convenience,
not security enforcement; Redis is authoritative after reloads and across tabs.

## Configuration

| Backend environment variable | Default |
| --- | --- |
| RATE_LIMIT_ENABLED | true |
| RATE_LIMIT_MUTATION_REQUESTS | 60 |
| RATE_LIMIT_MUTATION_WINDOW_SECONDS | 60 |

The limiter uses the existing REDIS_URL and REDIS_TIMEOUT_SECONDS. Production
requires a `rediss://` URL whenever caching or limiting is enabled. Disabling the
redirect cache does not disable the limiter. No new Render or Vercel variables
are required for the default policy. Deploy both services to receive backend
enforcement and the new frontend messages.

## Tests and deployment check

Ordinary backend tests disable external limiting to avoid shared counters between
fixtures. Dedicated limiter tests enable it explicitly. With LINKHUB_TEST_REDIS=1,
the real Redis test checks concurrent attempts from two limiter instances, separate
users, and expiry. It uses a unique prefix and cleans up only its own keys. The CI
workflow already enables this flag and runs the new tests automatically.

After CI passes and both services deploy, use a disposable account/link to check
the 429 response and Retry-After header after the configured number of mutations.
Verify listing and logout still work, and retry manually after the window expires.
Do not run load tests or consume another user's budget as a smoke test. Live limit
verification is separate from the local automated tests.
