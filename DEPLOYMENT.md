# LinkHub deployment checklist

The Vercel API rewrite points to https://linkhub-api-mtu1.onrender.com.
The frontend is https://linkhub-five-theta.vercel.app. Cloud resources are
configured separately using the steps below.

## 1. Create the database and cache

Create a Neon project and database. Choose a region close to the Render region.
Save the direct (non-pooled) PostgreSQL host, database, role, password and port
privately. For this initial single-instance deployment, use the direct endpoint
for both the application and Alembic migrations.

Create an Upstash Redis database nearby. Obtain its Redis protocol TLS connection
URL (`rediss://...`), not its REST endpoint. Keep it private.

## 2. Prepare public addresses

Create/import a Vercel project from the GitHub repository with root directory
`frontend`, framework Vite, install command `npm ci`, build command `npm run build`,
and output directory `dist`. Its initial dashboard can load, but authentication
will not work until the backend and rewrite are configured. Record its stable
production HTTPS origin, without a trailing slash. Preview URLs are not
automatically trusted by the backend.

Create a Render Python web service from the same repository with root directory
`backend`. Choose an instance plan deliberately. Free instances sleep after 15
minutes of inactivity and can take about a minute to wake, including for redirects.
Record the assigned HTTPS service origin. Select Python 3.13 through Render's
Python version configuration; if using PYTHON_VERSION, use a supported full 3.13.x
version. Do not rely on Render's changing default.

## 3. Configure Render

Set these variables in Render's environment settings. Values below are templates,
not credentials. Do not paste actual secrets into chat or Git.

| Variable | Value |
| --- | --- |
| ENVIRONMENT | production |
| DB_HOST | Neon direct endpoint hostname |
| DB_PORT | 5432 |
| DB_NAME | Your Neon database name |
| DB_USER | Your Neon role |
| DB_PASSWORD | Your Neon password |
| DB_SSLMODE | verify-full |
| DB_SSLROOTCERT | /etc/ssl/certs/ca-certificates.crt |
| JWT_SECRET | A stable cryptographically random secret, at least 32 characters |
| REFRESH_COOKIE_SECURE | true |
| AUTH_ALLOWED_ORIGINS | ["https://YOUR-PROJECT.vercel.app"] |
| REDIRECT_CACHE_ENABLED | true |
| REDIS_URL | Your private Upstash rediss:// URL |

Use a password manager's random generator for JWT_SECRET. Keep the same secret
across restarts. Use the explicit Linux CA bundle path above on Render:
DB_SSLROOTCERT=system failed certificate verification with this deployment's
binary driver. Keep DB_SSLMODE=verify-full to verify the certificate and hostname.

Render commands below run in its Linux service root (`backend`), not PowerShell:

- Build: `uv sync --frozen --no-dev`
- Start: `.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health-check path: `/health`

Run `.venv/bin/alembic upgrade head` before starting the first application version.
On a plan supporting a pre-deploy command, put it there. For an initial free,
single-instance service without pre-deploy support, use this start command:

```sh
.venv/bin/alembic upgrade head && exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

This free-service approach runs migrations at every start. Keep one instance and
avoid overlapping deploys; move migrations to a dedicated release step before
scaling. Review future schema migrations for compatibility with the running app.
Never run migration downgrade commands against production to test rollback.

The health endpoint checks that the web process responds; it does not prove that
database, Redis, or authentication are working.

## 4. Connect Vercel to Render

The Render origin in `frontend/vercel.json` is configured for this deployment.
If the backend address changes, update it and keep `/api/:path*` appended.
This is a literal URL: Vercel JSON does not substitute a Vite environment variable.

In Vercel's production environment settings set:

```text
VITE_PUBLIC_BACKEND_URL=https://linkhub-api-mtu1.onrender.com
```

This URL is public and is embedded into the frontend build. Never put secrets in
VITE_ variables. The local development fallback remains the frontend origin,
with Vite forwarding `/r/` and `/api` to the local backend.

Review, commit and push the configuration changes to the deployment branch when
ready. Redeploy both services from that version. Updating a Vercel environment
variable requires a new build. If the Vercel production domain changes, update
Render's AUTH_ALLOWED_ORIGINS as well.

The browser calls Vercel `/api`; Vercel forwards to Render. The refresh cookie
remains HttpOnly, Secure and SameSite=Strict, scoped to `/api/auth`, with no Domain
attribute. Confirm cookie forwarding on the real deployment. Do not enable broad
CORS or weaken origin checks to hide a proxy configuration error.

## 5. Verify the live deployment

- Visit Render `/health`; expect `{"status":"ok"}`.
- Register a disposable account through Vercel, log in, reload, then log out.
  Confirm reloading after logout keeps you signed out.
- Create a link. Check the displayed/copied URL starts with the Render origin.
- Open it and verify the destination and click count after reloading the list.
- Edit the destination after visiting once, then verify the cached redirect updates.
- Disable, expire and delete links; each must return 404 at its public URL.
- In browser developer tools verify API requests use the Vercel origin and the
  refresh cookie has Secure, HttpOnly, SameSite=Strict and path /api/auth. Never
  share the cookie or Authorization header values.
- Check service logs for failures without sharing credentials or connection URLs.

GitHub Actions CI is defined in `.github/workflows/ci.yml`; see `CI.md` for the
walkthrough. It runs checks, not deployments. A passing workflow does not by itself
block merges or gate Vercel deployments. Configure required checks and deployment
gates separately. Rate limiting remains pending.

## References

- https://vercel.com/docs/frameworks/frontend/vite
- https://vercel.com/docs/routing/rewrites
- https://render.com/docs/deploy-fastapi
- https://render.com/docs/deploys
- https://render.com/docs/python-version
- https://render.com/docs/free
- https://neon.com/docs/security/security-overview
- https://upstash.com/docs/redis/features/security
