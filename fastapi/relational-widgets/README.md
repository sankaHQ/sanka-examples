# FastAPI relational widgets to Go

This synthetic FastAPI app has parent and widget tables, a foreign key, a
non-unique index, and three linear Alembic revisions. The third adds a required
boolean column with a static default and a nullable text column to existing
widget rows. Eight CRUD routes exercise
successful writes, updates, deletes, unique-key conflicts, and foreign-key
conflicts. The checked-in `sanka-verify.json` holds the ordered HTTP cases.

The Python-to-Go converter lowers these revisions to Goose migrations and the
routes to Go/Fiber, chi, mux, or Gin. The acceptance runner uses the published
Sanka CLI 0.3.0 and a pinned public converter release. For each router it creates
four disposable PostgreSQL schemas: two for `scan`, `plan`, `apply`, `test`, and
`verify`, and two for an existing-row transfer. It applies the source Alembic
revisions, seeds related rows, applies generated Goose migrations to an empty
target, checks transfer dry-run/execute/verify, compares source and Go HTTP and
database state, and rolls back both generated targets. All schemas are dropped
even when a check fails. Nothing is deployed.

The source files are in [`source/`](source/). They use a linear migration chain,
direct SQLAlchemy sessions, and a single foreign-key relationship. Alembic's
conventional `env.py` is omitted because it is outside that profile; the CLI
verifier runs the checked-in
revisions against the disposable source schema. For an independent source
process, supply a PostgreSQL `DATABASE_URL` whose `parents` and `widgets`
tables have been initialized from those revisions, then run `uvicorn app:app`
from `source/`.

## Reproduce

Python 3.12, `uv`, Git, Go 1.26.5, and a local PostgreSQL database are required.
The database role must be able to create and drop schemas. Use a disposable
database; the runner never touches existing application schemas.

The published `api-converters-v0.1.0a8` release is pinned to merge commit
`4e7e66ea5141232cd61ab8c2886a3d496d130b67`. Run from the repository root:

```sh
export SANKA_MIGRATE_TEST_POSTGRES_DSN='postgresql://USER:PASSWORD@127.0.0.1:5432/sanka_example'
uv run --no-project --python 3.12 --with 'psycopg[binary]==3.3.4' \
  python fastapi/relational-widgets/scripts/accept_migration.py --target fiber
```

The other qualified targets are `chi`, `mux`, and `gin`. CI runs each target
independently. The fixture seeds two parents and three widgets with nontrivial ID
sequence state. The transfer requires explicit acknowledgement of its excluded
`alembic_version` table, verifies copied rows and sequences, rejects a second
copy into the nonempty target, and compares seven further HTTP requests and the
resulting database state. A real transfer requires a source write freeze and an
application-specific plan for excluded tables and jobs.

The runner installs the source dependencies from `source/requirements.txt`
into an isolated environment. It installs the converter through the CLI's
public marketplace at the pinned release commit; no adjacent Extensions
checkout or local wheel is used. Raw local artifacts go under ignored `.sanka/`.

This synthetic example does not support Alembic branches or schema changes
beyond the bounded add-column case. It does not synchronize writes after
transfer or qualify a production cutover.

The [acceptance evidence](evidence.json) records all five CLI stages, 17
source-to-Go observations and seven post-transfer HTTP comparisons per router,
equal rows, indexes and sequences, default backfill of existing rows, refusal
of unsafe transfer attempts, and successful rollbacks.
