# FastAPI relational widgets to Go

This synthetic FastAPI app has parent and widget tables, a foreign key, a
non-unique index, and two linear Alembic revisions. Eight CRUD routes exercise
successful writes, updates, deletes, unique-key conflicts, and foreign-key
conflicts. The checked-in `sanka-verify.json` holds the ordered HTTP cases.

The Python-to-Go converter lowers these revisions to Goose migrations and the
routes to Go/Fiber. The acceptance runner uses the published Sanka CLI 0.3.0
and a pinned public converter release. It creates separate disposable PostgreSQL
schemas, runs `scan`, `plan`, `apply`, `test`, and `verify`, compares source and Go
HTTP/database state, then runs the generated rollback. It drops both schemas
even when a check fails. Nothing is deployed.

The source files are in [`source/`](source/). They match the qualified a6
FastAPI profile: one linear migration chain, direct SQLAlchemy sessions, and a
single foreign-key relationship. Alembic's conventional `env.py` is omitted
because it is outside that profile; the CLI verifier runs the checked-in
revisions against the disposable source schema. For an independent source
process, supply a PostgreSQL `DATABASE_URL` whose `parents` and `widgets`
tables have been initialized from those revisions, then run `uvicorn app:app`
from `source/`.

## Reproduce

Python 3.12, `uv`, Git, Go 1.26.5, and a local PostgreSQL database are required.
The database role must be able to create and drop schemas. Use a disposable
database; the runner never touches existing application schemas.

The published `api-converters-v0.1.0a6` release is pinned to merge commit
`5b7fdeb80c524d87795ddae75ea356d00cea0d12`. Run from the repository root:

```sh
export SANKA_MIGRATE_TEST_POSTGRES_DSN='postgresql://USER:PASSWORD@127.0.0.1:5432/sanka_example'
uv run --no-project --python 3.12 --with 'psycopg[binary]==3.3.4' \
  python fastapi/relational-widgets/scripts/accept_migration.py
```

The runner installs the source dependencies from `source/requirements.txt`
into an isolated environment. It installs the converter through the CLI's
public marketplace at the pinned release commit; no adjacent Extensions
checkout or local wheel is used. Raw local artifacts go under ignored `.sanka/`.

This example does not transfer existing application data, support branching or
schema-altering Alembic migrations, or qualify a production cutover. Fiber is
the public walkthrough target; the Extensions a6 tests also exercise chi, mux,
and Gin against PostgreSQL.

The [acceptance evidence](evidence.json) records 17 matching HTTP and database
observations, equal indexes, a successful rollback, and all five CLI stages.
