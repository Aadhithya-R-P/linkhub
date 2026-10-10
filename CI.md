# Understanding LinkHub CI

Continuous integration (CI) automatically checks code changes in a clean environment.
Our workflow is `.github/workflows/ci.yml`. GitHub reads it after it is pushed.
It does not run on a local save, `git add`, or a local commit alone.

## What happens

A push to main, a pull request targeting main, or a manual run starts CI. Two jobs
run independently on separate Ubuntu machines: frontend tests/build, and backend
tests/migrations. Steps within a job run in order. A failing command stops the
remaining ordinary steps in that job and makes the check fail; the other job can
still finish. A green run means the configured checks passed, not that deployment
or every possible user interaction has been verified.

## Workflow walkthrough

Read the YAML from top to bottom. Indentation determines nesting, `-` introduces
a list item, and `${{ ... }}` is an expression evaluated by GitHub.

| YAML entry | Meaning |
| --- | --- |
| `name: CI` | Name shown in the Actions tab. |
| `on` | Events that start the workflow. |
| `push`, `branches: [main]` | Run when commits reach main, including merges. |
| `pull_request`, `branches: [main]` | Run for PRs targeting main; this filters the destination branch. By default, PR runs test a synthetic merge with the target branch. |
| `workflow_dispatch` | Offer a manual Run workflow button once the workflow exists on the default branch. |
| `permissions`, `contents: read` | Give the workflow token read access to repository contents; unspecified permissions are disabled. |
| `concurrency` | Control overlapping runs. |
| `group` | Combine workflow name and Git ref into a group; different PR refs get different groups. |
| `cancel-in-progress: true` | Cancel an older run in the same group when newer code arrives. |
| `jobs` | Define independent units of work. |
| `frontend` / `backend` | Internal job IDs. No `needs` dependency means they may run concurrently. |
| Job `name` | Friendly name displayed in GitHub checks. |
| `runs-on: ubuntu-24.04` | Use a fresh GitHub-hosted Ubuntu runner. Your Windows computer is not running these commands. |
| `timeout-minutes` | Stop a stuck job after 10 minutes for frontend or 15 for backend. |
| `defaults`, `run`, `working-directory` | Set the folder for shell command steps in that job. This does not change action input paths. |
| `steps` | Ordered list of actions and commands. |
| Step `name` | Human-readable label in the run log. |
| `uses: actions/checkout@v6` | Download the repository for this run using version 6 of the checkout action. Each job needs its own checkout. |
| `uses: actions/setup-node@v6` | Install/select Node for the frontend job. |
| `with` | Supply inputs to an action. |
| `node-version: '24'` | Select Node 24, independently of the setup action's version. |
| `cache: npm` | Reuse downloaded npm packages to speed up installs; this does not skip dependency installation or tests. |
| `cache-dependency-path` | Use frontend/package-lock.json to identify dependency-cache changes; path is relative to the repository root. |
| `run: npm ci` | Install exactly from package-lock.json; fail if package.json and the lockfile disagree. |
| `run: npm test` | Run the package.json test script, currently vitest run. |
| `run: npm run build` | Run the Vite production build; generated dist files stay on the temporary runner. |
| `services` | Start temporary containers alongside the backend runner. |
| `postgres`, `image: postgres:17` | Start PostgreSQL 17. This is independent of your Neon database. |
| Service `env` | Environment variables passed to that container. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Initialize an empty CI database and its login. Values are intentionally public, disposable test credentials. |
| `ports`, `5432:5432` | Map runner port 5432 to PostgreSQL container port 5432. |
| `options: >-` | Fold the following YAML lines into one Docker options string. |
| `--health-cmd` | Check that PostgreSQL accepts connections; for Redis, check it responds to ping. |
| `--health-interval 10s` | Check service health every 10 seconds. |
| `--health-timeout 5s` | Allow each check up to five seconds. |
| `--health-retries 5` | Mark a service unhealthy after five consecutive failures. GitHub waits for healthy services before running the job's steps. |
| `redis`, `image: redis:7-alpine` | Start a small Redis 7 container. This is the Redis server version, not the Python redis package version. |
| `6379:6379` | Make Redis available at runner localhost port 6379. |
| Job `env` | Environment variables available to the backend steps, separate from container initialization settings. |
| `ENVIRONMENT: development` | Use local-style settings for isolated HTTP tests. Production configuration rules have separate unit tests. |
| `DB_HOST: 127.0.0.1` | Connect through the runner's published service port. |
| `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Match the PostgreSQL service's connection details. |
| `DB_SSLMODE: disable` | The disposable local service is not configured with production certificates. Production still requires verified TLS. |
| `JWT_SECRET` | A test-only signing key satisfying the minimum length; never use this value in production. |
| `REFRESH_COOKIE_SECURE: 'false'` | Allow cookies with the in-process HTTP test client. |
| `REDIS_URL` | Point to temporary Redis, not Upstash. |
| `LINKHUB_TEST_DB: '1'` | Enable existing PostgreSQL tests that otherwise skip. |
| `LINKHUB_TEST_REDIS: '1'` | Enable the real Redis integration test. |
| `uses: astral-sh/setup-uv@v9` | Install uv, the backend dependency and environment manager. |
| `version: '0.13.0'` | Select the uv tool version, independently of the action version. |
| `python-version: '3.13'` | Select Python 3.13 for the backend. |
| `uv sync --locked --dev` | Create the virtual environment from uv.lock, include development dependencies such as pytest, and reject an outdated lockfile. |
| `uv run --locked alembic upgrade head` | Create the schema in empty CI PostgreSQL by applying the full migration chain. |
| `uv run --locked alembic check` | Detect model/schema differences that would require a generated migration. It does not create a migration file. |
| `uv run --locked pytest -q -ra` | Run backend tests in that environment; -q reduces chatter and -ra reports non-passing outcomes including skips. |

The database/cache containers are discarded after the job. Tests can create and
delete data there without touching production. GitHub does not receive your local
ignored .env file. No GitHub production secrets are needed for this workflow.

## Reading the first run

After committing and pushing, open GitHub repository > Actions > CI > latest run.
Open each job and its steps. If a job fails, start with the first failed step and
read the error above the final exit-code message. Check for unexpectedly skipped
integration tests even if the job is green. Fix the source of the failure locally,
then commit and push again; the new run checks the new revision.

## CI and deployment

This workflow is CI only. It does not publish to Vercel or Render. Vercel's existing
Git integration may deploy independently, even if these tests fail. To require a
passing check before merging, configure GitHub branch protection/rulesets with
both job checks after the first run. Deployment gates require separate setup.
No branch protections or hosting settings were changed by adding this workflow.

## References

- https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
- https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers
- https://docs.astral.sh/uv/guides/integration/github/
