# Flask status API → Go / Fiber

A runnable synthetic Python application with two public, literal JSON GET routes.
The experimental `sanka/python-to-golang` extension generates the Fiber application
under ignored `.sanka/` artifacts. There is no hand-maintained Go implementation.

This example is original synthetic Sanka example code, licensed under Apache-2.0
([license](source/LICENSE)). It contains no customer data, credentials, databases,
or model calls. Dependency packages retain their respective licenses.

## Source application

Use Python 3.12 and `uv`. From the repository root:

```sh
uv venv --python 3.12 flask/status-api/.venv
uv pip install --python flask/status-api/.venv/bin/python \
  -r flask/status-api/source/requirements.txt
flask/status-api/.venv/bin/python flask/status-api/scripts/check_source.py
flask/status-api/.venv/bin/python -m flask \
  --app flask/status-api/source/app.py run --host 127.0.0.1 --port 5050 --no-reload
```

The final command runs a local development server; stop it with Ctrl-C. All seven
runtime dependencies are pinned, including Flask 3.1.2 and Werkzeug 3.1.3.
The source root contains only the application, dependency pins and license;
test and migration scripts live outside it because this capture profile rejects
additional unrelated Python modules.

In another terminal:

```sh
curl -i http://127.0.0.1:5050/health
curl -i http://127.0.0.1:5050/info
```

| Request | Status | Media type | JSON body |
| --- | --- | --- | --- |
| `GET /health` | `200` | `application/json` | `{"status":"ok"}` |
| `GET /info` | `200` | `application/json` | `{"service":"status-api","version":1,"read_only":true}` |

The generated destination must return the same statuses, media types and parsed
JSON bodies. JSON whitespace, property order and optional Content-Type parameters
are not compared. [expected.json](expected.json) is the executable contract.

## Pinned migration candidate

This extension is **experimental and unpublished in its catalog** at candidate
[`83e290614b784dab33e7271ecb8533a726e111d2`](https://github.com/sankaHQ/extensions/commit/83e290614b784dab33e7271ecb8533a726e111d2),
the unmerged source-interpreter candidate in [extensions PR #95](https://github.com/sankaHQ/extensions/pull/95).
The package version is `0.1.0a1`; the candidate commit identifies its implementation.
This walkthrough uses published `sanka-cli==0.2.12`, extension SDK `0.1.0a4`, and
Go **1.26.5**. No Sanka Python/Node client SDK is used.

The [shared candidate installer](../../scripts/candidate.py) fetches that exact
public Git commit, checks its catalog, builds the converter wheel with pinned build
dependencies, verifies the SDK release wheel checksums, and installs through a
temporary local marketplace using the public CLI. Its isolated HOME and extension
store prevent reliance on a sibling checkout or a user's installed extensions.
Do not substitute a public-catalog installation command: this converter is not
published there.

The source dependencies are installed into a separate Python 3.12 environment.
The runner sets `SANKA_GO_SOURCE_PYTHON` to that environment's absolute Python path
and explicitly forwards it with `--extension-env SANKA_GO_SOURCE_PYTHON`. Verification
uses this interpreter with Python isolation (`-I`), leaving the locked converter
environment untouched. PR #95 adds that supported source-interpreter selection;
the earlier candidate could not replay Flask from a clean locked installation.

## Reproduce acceptance

Requirements: Python 3.12, `uv`, Git, OpenSSL and a supported macOS/Linux host.
First-time setup downloads public wheels, the immutable converter source, the
checksum-pinned Go 1.26.5 compiler if needed, and Go modules. No customer service,
private Sanka service or paid inference is contacted. The application checks use
loopback HTTP only. Dependency setup needs network access; warmed source checks
run offline.

From the repository root, after installing the source dependencies above:

```sh
flask/status-api/.venv/bin/python flask/status-api/scripts/accept_migration.py
```

The script performs a fresh candidate installation and runs these public lifecycle
commands in a clean source copy (the installer provides the isolated `sanka`
executable and `SANKA_GO_SOURCE_PYTHON` environment):

```sh
sanka scan . --extension-config '{"source_framework":"flask","target_framework":"fiber","source_file":"app.py","database_layer":"none"}' --extension-env SANKA_GO_SOURCE_PYTHON --json
sanka plan . --to fiber --extension-config '{"source_framework":"flask","target_framework":"fiber","source_file":"app.py","database_layer":"none"}' --extension-env SANKA_GO_SOURCE_PYTHON --json
# Review the captured routes, empty gaps and generated files in the plan.
# Use the exact core plan_hash from the plan response, not extension.plan_hash.
sanka apply --plan-hash "$REVIEWED_PLAN_HASH" --extension-env SANKA_GO_SOURCE_PYTHON --json
sanka test --extension-env SANKA_GO_SOURCE_PYTHON --json
sanka verify --extension-env SANKA_GO_SOURCE_PYTHON --json
```

The acceptance script reviews the known fixture automatically: it requires an
empty gap list, the expected runnable target files, identical repeated plan hashes,
and rejection of an incorrect reviewed hash before applying the exact returned
hash. It checks every generated file against the plan, then executes `test` and
`verify`. Both must explicitly pass. The extension's own replay uses the actual
Flask and Go request clients.

It additionally runs `go test ./...`, `go vet ./...`, and
`go build -o <temporary-binary> ./cmd/api` with Go 1.26.5, starts the real Flask and
compiled Fiber servers on temporary loopback ports, and compares both live HTTP
responses to the explicit contract. It stops both servers and proves that original
source, copied source and generated source were unchanged by verification.

Each successful run retains generated Go files and raw stage reports in a new
`flask/status-api/.sanka/accepted-*/` directory. The latest report is
`flask/status-api/.sanka/acceptance.json`; failures replace it with failure evidence.
The report records tool versions, candidate wheel hashes, source digests, both
plan hashes, generated file digests and actual HTTP observations. Core plan hashes
include environment-specific installation/artifact paths; compare the extension
plan hash and generated file hashes across clean runs.

To run retained output, change into its `golang/` directory and use Go 1.26.5:

```sh
go test ./...
go vet ./...
go build -o .sanka-api ./cmd/api
PORT=5051 ./.sanka-api
```

Stop the server with Ctrl-C. `curl -i http://127.0.0.1:5051/health` and
`curl -i http://127.0.0.1:5051/info` must match the table above. The build executable
is an ignored local artifact, outside the recorded generated-source digest set.

## Acceptance boundary

[evidence.json](evidence.json) records the implementation
run. CI repeats the same acceptance rather than trusting that historical snapshot.
The scope is exactly the two successful GET responses. Database operations,
writes, middleware, authentication, default errors, HEAD/OPTIONS, redirects,
content negotiation, deployment and whole-application parity are not established.
Other Go routers and Go-source migrations are not demonstrated by this example.
