# Gadget inventory: DRF to FastAPI, Flask or Go

This shared public-guide example exposes a `Gadget` model through a DRF
`ModelViewSet`, with JSON responses, validation and CRUD. The committed SQLite
database is example data. Use a separate checkout and disposable databases.
See [Python migration setup](../../PYTHON_MIGRATIONS.md) for Docker/Podman,
PostgreSQL and the current Go SQLite release status.

## Source environment

Install the published CLI separately from the application environment. No extra
marketplace alias is required; existing project locks are not automatically repinned.

```bash
uv tool install sanka-cli==0.3.6
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
unset SANKA_TEST_DB
```

For PostgreSQL, select the checked-in settings template, set `SANKA_TEST_DB`
before Scan and Plan and initialize that
disposable source with `manage.py migrate`. See the shared setup below.

## DRF to FastAPI or Flask

Choose `TARGET=fastapi` or `TARGET=flask` once:

```bash
TARGET=fastapi
sanka extension add "sanka/drf-to-$TARGET"
sanka scan .
sanka plan . --to "$TARGET" --strategy native --generation minimal \
  --package-manager uv --output ".sanka/output/$TARGET" --all-endpoints \
  --extension-config '{"settings_module":"crud_config.settings","db_env":"SANKA_TEST_DB","database_backend":"sqlite"}'
```

Review supported endpoints, gaps, output and the returned plan hash. For partial
migration, inspect endpoint IDs in `sanka scan . --json`, then replace
`--all-endpoints` with repeated `--endpoint '<id>'` flags. Replanning changes the hash.

```bash
sanka apply --root . --plan-hash '<reviewed-plan-hash>'
sanka test .
```

FastAPI's Test step creates the generated application's `.venv`. For Flask's
Django ORM profile, install target dependencies in the source environment:

```bash
uv pip install --python .venv/bin/python Flask httpx SQLAlchemy
```

`scenarios.json` contains eight independent replay cases, including browser
Accept headers and a missing-record response. For FastAPI:

```bash
sanka verify . --scenarios scenarios.json \
  --candidate .sanka/output/fastapi --settings crud_config.settings \
  --db-env SANKA_TEST_DB --source-python "$PWD/.venv/bin/python" \
  --candidate-python "$PWD/.sanka/output/fastapi/.venv/bin/python" \
  --extension-config '{"entrypoint":"app.py"}'
```

For Flask:

```bash
sanka verify . --scenarios scenarios.json \
  --candidate .sanka/output/flask --settings crud_config.settings \
  --db-env SANKA_TEST_DB --source-python "$PWD/.venv/bin/python" \
  --candidate-python "$PWD/.venv/bin/python" \
  --extension-config '{"entrypoint":"target_app.py"}'
```

Public Flask a14 currently returns a different missing-record detail from DRF.
Keep that scenario: Verify should report the mismatch until the extension fix
is released. Passing generated tests alone is not parity evidence.
Public FastAPI a20 passes all eight SQLite scenarios. PostgreSQL Verify currently
fails because the shared replay helper passes an incompatible driver URL; that
fix also remains an unpublished candidate.

## DRF to Go

`sanka-verify.json` contains 13 ordered HTTP scenarios for Go, covering all six
endpoint methods, including full PUT replacement, required-field validation and
a missing-record update. GET after PUT checks the persisted replacement. Its
format differs from the independent DRF replay file above.

Public CLI 0.3.6 and Go extension a14 detect the DRF project and SQLite source.
The default SQLite target needs no Docker, Podman or database URL. Test and
Verify use isolated disposable SQLite databases and preserve the example data.

```bash
sanka extension add sanka/python-to-golang
export SANKA_GO_SOURCE_PYTHON="$PWD/.venv/bin/python"
sanka scan . --extension-env SANKA_GO_SOURCE_PYTHON
sanka plan . --to fiber --all-endpoints --extension-env SANKA_GO_SOURCE_PYTHON
```

Review the generated files, endpoint scope and plan hash, then:

```bash
sanka apply --root . --plan-hash '<reviewed-plan-hash>' --extension-env SANKA_GO_SOURCE_PYTHON
sanka test . --extension-env SANKA_GO_SOURCE_PYTHON
sanka verify . --extension-env SANKA_GO_SOURCE_PYTHON
```

Use `chi`, `mux` or `gin` instead of `fiber` for another router. To also run the
original Django tests during Verify:

```bash
export SANKA_GO_RUN_ORIGINAL_TESTS=1
sanka verify . --extension-env SANKA_GO_SOURCE_PYTHON \
  --extension-env SANKA_GO_RUN_ORIGINAL_TESTS
```

## CLI, AI Agent and TUI

Ordinary commands use the CLI. Agents can add `--json` or `--compact-dsl`,
inspect the outcome and stop on gaps or failures. For the same configuration
and endpoint selection in the TUI, run `sanka tui .` or add `--tui` explicitly.
Configure Plan before generating it. Generated requires an apply receipt plus
matching files; Verified is a separate parity result.
