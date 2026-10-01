# Python migration guide examples

Use a disposable checkout with published CLI 0.3.4. The official marketplace is
available by default: `sanka extension add sanka/python-to-golang` does not need
a `release` alias. Existing locks preserve their selected revision.

| Source | Example | Database |
| --- | --- | --- |
| Django / DRF | [Gadget inventory](django/gadget-inventory/README.md) | SQLite by default; PostgreSQL through `SANKA_TEST_DB` |
| FastAPI | [Relational widgets](fastapi/relational-widgets/README.md) | PostgreSQL with three Alembic revisions |
| Flask | [Status API](flask/status-api/README.md) | No persistence; HTTP example |

The Flask status example is not a database transfer test. Public Go a12 targets
PostgreSQL. Go SQLite-to-SQLite support is an unreleased candidate in
[Extensions #154](https://github.com/sankaHQ/extensions/pull/154).
SQLite-to-PostgreSQL and PostgreSQL-to-PostgreSQL are separate acceptance paths.

## Disposable PostgreSQL: Docker or Podman

Choose your installed runtime. On macOS, start the Podman machine first if
using Podman. A random localhost port avoids the guide's fixed-port collision.
Do not remove an existing container to free its port.

```bash
RUNTIME=docker # or: RUNTIME=podman
CONTAINER=sanka-guide-$(date +%s)
"$RUNTIME" run --name "$CONTAINER" -e POSTGRES_PASSWORD=guide \
  -p 127.0.0.1::5432 -d docker.io/library/postgres:16-alpine
for attempt in $(seq 1 30); do
  "$RUNTIME" exec "$CONTAINER" pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1 && break
  sleep 1
done
"$RUNTIME" exec "$CONTAINER" pg_isready -h 127.0.0.1 -U postgres
PORT=$("$RUNTIME" port "$CONTAINER" 5432/tcp | sed 's/.*://')
"$RUNTIME" exec "$CONTAINER" createdb -U postgres drf_source
"$RUNTIME" exec "$CONTAINER" createdb -U postgres target_test
export SANKA_TEST_DB="postgresql://postgres:guide@127.0.0.1:$PORT/drf_source"
export SANKA_DATABASE_URL="postgresql://postgres:guide@127.0.0.1:$PORT/target_test"
export SANKA_REPLAY_POSTGRES_ADMIN_DSN="postgresql://postgres:guide@127.0.0.1:$PORT/postgres"
export SANKA_GO_TARGET_TEST_DATABASE_URL="$SANKA_DATABASE_URL"
```

These credentials belong only to this local disposable example. Replay creates
isolated databases and removes only its own databases. Its role needs permission
to create databases. Never supply a production admin URL.
Stop if readiness or database creation fails.

## DRF with PostgreSQL

From `django/gadget-inventory`, initialize the disposable source:

```bash
cp crud_config/settings_postgresql.py.in crud_config/settings.py
uv pip install --python .venv/bin/python 'psycopg[binary]'
.venv/bin/python manage.py migrate
SANKA_TEST_DB="$SANKA_DATABASE_URL" .venv/bin/python manage.py migrate
```

Forward `SANKA_TEST_DB` on Scan and Plan so capture sees PostgreSQL. For FastAPI
or Flask, use these settings before reviewing the plan hash:

```bash
sanka scan . --extension-env SANKA_TEST_DB
sanka plan . --to "$TARGET" --strategy native --generation minimal \
  --package-manager uv --output ".sanka/output/$TARGET" --all-endpoints \
  --extension-config '{"settings_module":"crud_config.settings","db_env":"SANKA_TEST_DB","database_backend":"postgresql","postgres_admin_dsn_env":"SANKA_REPLAY_POSTGRES_ADMIN_DSN"}' \
  --extension-env SANKA_TEST_DB --extension-env SANKA_REPLAY_POSTGRES_ADMIN_DSN
sanka apply --root . --plan-hash '<reviewed-plan-hash>'
sanka test . --extension-env SANKA_TEST_DB --extension-env SANKA_DATABASE_URL
```

Use the target-specific Verify command in the example README, adding
`--extension-env SANKA_REPLAY_POSTGRES_ADMIN_DSN`. Install `SQLAlchemy` and
`psycopg[binary]` in the Flask candidate environment too. Configure the backend
in the reviewed plan; do not silently change it after Apply.

## Cleanup

After stopping your example apps, remove only the container you created:

```bash
"$RUNTIME" rm -f "$CONTAINER"
unset SANKA_TEST_DB SANKA_DATABASE_URL SANKA_REPLAY_POSTGRES_ADMIN_DSN
unset SANKA_GO_TARGET_TEST_DATABASE_URL
```

Generated tests and HTTP parity are separate checks. Preserve failed scenarios
and stop before claiming Verify success. Real applications need their own
scenarios for permissions, relationships and business logic.
