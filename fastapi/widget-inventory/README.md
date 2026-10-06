# FastAPI widgets with SQLite

A synthetic FastAPI and SQLAlchemy application for the Python-to-Go guide.
SQLite is the default database; no container or Sanka account is needed. The
separate PostgreSQL/Alembic example remains at [relational-widgets](../relational-widgets/).

The four write endpoints exercise creation, partial and full updates, deletion,
validation and missing records. The checked-in `sanka-verify.json` contains 16
ordered requests. Integer primary keys use SQLite ROWID allocation: deleting the highest
identifier permits reuse, matching this SQLAlchemy source and the generated Go app.

```bash
cd source
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python ../check.py
export DATABASE_URL="sqlite:///$PWD/widgets.sqlite3"
.venv/bin/python ../setup.py
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 18001
```

Keep the source database separate from the generated app. The Go extension's
Test and Verify stages create disposable databases and compare real HTTP
responses and stored rows. They do not qualify arbitrary application behavior.

Follow the [Python-to-Go guide](https://sanka.com/docs/developers/migrate/python-to-go/)
for public CLI installation, endpoint selection, reviewed Apply, Test and Verify.
Generated files belong under ignored `.sanka/` paths; do not edit a second
checked-in target application.

Apache-2.0. This is a synthetic Sanka example adapted from the converter's
existing qualified SQLite write fixture.

Historical Go a13 acceptance passed Scan, Plan, Apply, Test and Verify on Fiber,
chi, mux and Gin with public CLI 0.3.4. See [evidence.json](evidence.json) for
exact identities, source and generated hashes, and bounded comparison scope.

To repeat that historical public installed-converter check (downloads dependencies):

```bash
python3 accept_migration.py --router fiber --report .sanka/acceptance.json
```

Choose `chi`, `mux` or `gin` for the other qualified routers. The helper uses the
shared published installer, pins a13, and preserves the source.
