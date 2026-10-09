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
Daily trends and charts are out of scope. Redirect caching is not implemented yet.
Future server-side cache hits must still record clicks.

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
