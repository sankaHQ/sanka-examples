# Spring Boot orders → FastAPI + PostgreSQL

This synthetic Apache-2.0 example migrates one flat JPA resource through all five
public CLI stages. The unpublished a2 candidate handles validated JSON requests,
explicit errors, exact decimal strings, CRUD and rollback after a database flush.
It retains PostgreSQL; it does not migrate production data or change a schema.

Three source JUnit tests cover persistence, validation and rollback. Test runs
43 generated Python cases. Verify compares Spring MockMvc with FastAPI TestClient,
including every table row and the identity sequence after each request. The
walkthrough deliberately changes a database write while retaining its response
and requires Verify to reject it. See [evidence.json](evidence.json) for the actual
observations, file hashes and immutable converter revision.

## Prepare the pinned candidate

Use macOS or Linux, Java 21, PostgreSQL 17.11 tools on PATH, Git, OpenSSL and uv
0.11.21. The commands below start a separate task-owned PostgreSQL server. No
existing database is reset. Run from this example directory:

```sh
JAVA_CONVERTER_REVISION=$(python3 -c 'import json; print(json.load(open("migration.json"))["destinations"][0]["candidate_revision"])')
git clone https://github.com/sankaHQ/extensions .sanka/extensions
git -C .sanka/extensions checkout --detach "$JAVA_CONVERTER_REVISION"
cd .sanka/extensions
python3 scripts/fetch_java_parser.py
python3 scripts/fetch_java_maven.py
uv sync --frozen --all-packages
uv venv --python 3.12.13 .java-tools/python
uv pip sync --python .java-tools/python/bin/python --require-hashes \
  packages/sanka-extension-java-to-python/src/sanka_extension_java_to_python/requirements.lock
python3 scripts/java_postgres.py start --root "$PWD/.java-tools/postgres"
export SANKA_JAVA_REPLAY=1
export SANKA_JAVA_POSTGRES_CONFIG="$PWD/.java-tools/postgres/connection.json"
export SANKA_JAVA_MAVEN="$PWD/.java-tools/apache-maven-3.9.16/bin/mvn"
export SANKA_JAVA_MAVEN_REPO="$PWD/.java-tools/maven-repository"
export SANKA_JAVA_PYTHON="$PWD/.java-tools/python/bin/python"
uv run python scripts/prepare_java_fixture.py --fixture packages/sanka-extension-java-to-python/tests/fixtures/orders
uv run python scripts/build_java_release.py
cd ../..
python3 check.py --bundle .sanka/extensions/release/java-converters
```

Preparation downloads dependencies and executes the trusted synthetic fixture.
Scan only parses source. Test and Verify execute code in disposable copies;
these copies are not a security sandbox. The harness installs CLI 0.3.9 and
checksum-verified wheels through a temporary HTTPS marketplace, then runs Scan,
Plan, Apply with the reviewed hash, Test and Verify.

Native JUnit, source replay and destination checks use separate uniquely named
databases. Only databases created by that invocation are dropped. The private
connection file is forwarded explicitly; its contents are never part of evidence.
The helper retains `.sanka/python-fastapi` and writes `.sanka/evidence.json`.
Move existing generated output before rerunning. CI adds `--check-evidence` to
compare fresh portable results with the committed receipt.

Stop the task-owned server when finished:

```sh
python3 .sanka/extensions/scripts/java_postgres.py stop --root "$PWD/.sanka/extensions/.java-tools/postgres"
```

## Exercise the generated service

The output runs with Python alone. Prepare a new empty PostgreSQL database and
apply its reviewed `schema.sql` separately. Startup never creates or alters tables.
Set `DATABASE_URL` privately to that database using the `postgresql+psycopg://`
scheme. From `.sanka/python-fastapi`:

```sh
uv venv --python 3.12.13 .venv
uv pip sync --python .venv/bin/python --require-hashes requirements.lock
.venv/bin/python -m uvicorn app:app --port 8000
```

In another terminal, create and inspect an order:

```sh
curl -i http://127.0.0.1:8000/orders/new -H 'Content-Type: application/json' \
  -d '{"name":"Invoice","amount":"999999999999.99","note":null}'
curl http://127.0.0.1:8000/orders/1
curl http://127.0.0.1:8000/orders/all
```

PUT `/orders/{id}` accepts the same body. DELETE returns an empty 204. Invalid
input returns `400 {"code":"invalid_request"}`; missing rows return
`404 {"code":"not_found"}`. POST `/orders/rollback` deliberately returns
`409 {"code":"rejected_write"}` after flush: the row is rolled back, but the
identity value remains consumed. This PostgreSQL behavior is part of verification.
`python -m pytest` executes the ordered scenario corpus and requires an empty,
disposable fixture database.

## Qualified scope

The source uses Spring Boot 3.5.16, JPA, explicit transactional repository idioms,
a validated input record and a complete exception advice. Decimal JSON is a string;
tests preserve its precision and scale. Cases include invalid updates, nulls,
blank text, UTF-16 length, numeric coercion, negative zero and identifier overflow.

This is a closed single-entity profile. Unknown source patterns block generation.
Authentication, authorization, relations, custom queries, concurrent writes,
arbitrary headers, live TCP behavior and production cutover are not qualified.
There is no generally available Java runner or published marketplace package.
