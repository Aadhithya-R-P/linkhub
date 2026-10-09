# LinkHub backend

## Click recording

Each successful `GET /r/{code}` records one row in `click_events` before returning
the redirect. Repeated requests, bots, and link previews count; these are not
unique visitors or proof that the destination loaded. Missing, disabled, expired,
and malformed links do not record clicks. HEAD requests are not supported.

Events contain an ID, link ID, and timezone-aware timestamp. The composite index
on `(link_id, clicked_at)` supports per-link totals and time-range queries. Hard
deleting a link cascades to its events. No IP addresses, referrers, or user agents
are stored.

Recording is synchronous and adds a database write to each successful redirect.
A database error during recording triggers rollback and a generic warning without
SQL parameters or request data; the redirect still uses the previously retrieved
destination. Counts can therefore underreport during failures. Lookup failures
are not treated as analytics failures. Redirect responses retain `no-store`.

Link listing and update responses include `total_clicks`; newly created links
return zero. Listing counts events for the requested page in one grouped query,
after selecting the owner's links. No separate analytics endpoint is needed.
Daily trends and charts are out of scope. Cache hits also record clicks.

## Redis redirect cache

Redirects check Redis before reading the link from PostgreSQL. A miss reads and
validates the link, then caches its destination and expiration under
`linkhub:redirect:v1:<link_id>`. Only available links are cached. Every cache hit
checks `expires_at` against current UTC time before redirecting. Redis uses a
fixed TTL; hits do not extend it, and TTL is not shortened for expiring links.

Successful edits and deletions invalidate the entry after the PostgreSQL commit.
Redis read failures and malformed entries fall back to PostgreSQL. Cache-write
failures do not block redirects, and invalidation failures do not undo successful
database changes. Logs omit exception details and connection credentials.

Configuration (environment variables or backend `.env`; restart after changes):

| Variable | Default |
| --- | --- |
| `REDIRECT_CACHE_ENABLED` | `true` |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` |
| `REDIRECT_CACHE_TTL_SECONDS` | `30` |
| `REDIS_TIMEOUT_SECONDS` | `0.2` |

The client uses a shared connection pool, short connection/read timeouts, and no
automatic retries. Disabling the cache bypasses both cache reads and invalidation;
allow old entries to expire before re-enabling it after mutations.

Accepted learning-project limitation: invalidation failure, a process crash, or
an overlapping lookup can leave stale data, including disabled/deleted links.
There are no distributed locks or version checks. Thirty seconds limits each
entry's lifetime, not staleness measured from an edit: a delayed lookup can write
an old value later. Changing expiration can likewise leave an old expiration
cached. Direct database edits bypass invalidation. A cached deleted link can
still redirect even though its analytics insert fails the foreign-key check.

PostgreSQL remains necessary for click recording; the cache saves link reads,
not analytics writes. Browser responses continue to use `Cache-Control: no-store`.

For local Windows development, Redis runs inside Ubuntu WSL. In Ubuntu (any
working directory), use `sudo service redis-server start` and `redis-cli ping`.
The Windows backend connects through `127.0.0.1:6379`. Keep Redis private to the
local machine; production requires its own secured Redis configuration.

To include the real Redis integration test, run from `D:\Projects\LinkHub\backend`:

```powershell
$env:LINKHUB_TEST_DB = '1'
$env:LINKHUB_TEST_REDIS = '1'
.\.venv\Scripts\python.exe -m pytest -q
```

Ordinary tests bypass external Redis. Redis integration uses a unique test prefix
and deletes only its own key; it never flushes the Redis database.

## Local migration and checks (PowerShell)

Working directory: `D:\Projects\LinkHub\backend`.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
$env:LINKHUB_TEST_DB = '1'
.\.venv\Scripts\python.exe -m pytest -q
```

Database tests require local PostgreSQL. Most use rolled-back transactions;
identity sequences can still advance. The click-events migration downgrade drops
the events table and its analytics history.
