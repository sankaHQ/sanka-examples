# Express status API to Rust / axum

A synthetic TypeScript / Express app with two public, literal JSON GET endpoints.
The experimental, published `sanka/typescript-to-rust` extension generates a Rust
crate; this example makes no claim about arbitrary TypeScript applications or Rust
source migrations. Source and scripts are Apache-2.0; see [LICENSE](LICENSE).
Dependencies retain their own licenses. No customer data or services are used.

## Run and check the source

Use macOS or Linux with npm, Python 3.12, Git, OpenSSL and uv. Installation downloads
public dependencies; application execution has no network dependency beyond local
HTTP. `package-lock.json` pins the full npm dependency tree. The project installs
Node 22.14.0 locally, without replacing your global Node installation.

```bash
cd express/status-api
npm ci --no-audit --no-fund
npm run check
npm start
```

`npm run check` compiles with TypeScript 5.8.2 and starts the actual source launcher
on an available loopback port to check both responses. `npm start` serves on
127.0.0.1:3000; stop with Ctrl-C. To choose a port, use `PORT=3001 npm start`.
The source dependency is Express 5.2.1. `src/app.ts` exports the application;
`src/server.ts` only imports it and calls `app.listen`, matching captured syntax.
Compilation goes into ignored `.sanka/source/`.

From another terminal while `npm start` is running:

```bash
curl -i http://127.0.0.1:3000/health
curl -i http://127.0.0.1:3000/status
```

| Request | Status | Exact JSON body |
| --- | --- | --- |
| `GET /health` | 200 | `{"status":"ok"}` |
| `GET /status` | 202 | `{"service":"status-api","ready":true,"revision":1}` |

Express sends `Content-Type: application/json; charset=utf-8`; axum sends
`Content-Type: application/json`. Both have the same `application/json` media type.
The example checks exact body bytes as well as status and parsed JSON.

## Reproduce the migration

Install Rust **1.93.1** using rustup before running acceptance. The generated
`Cargo.lock` pins Rust dependencies. The check requires public download access
for setup, wheel installation and the first Cargo build; conversion and HTTP
replay use no private service, credentials or inference. On macOS, select the
Command Line Tools SDK for the Rust build (required when the Xcode license is not
accepted, and also with Xcode 27, whose SDK stubs fail the Rust 1.93.1 linker with
`ld: tapi error: malformed file`):

```bash
export DEVELOPER_DIR=/Library/Developer/CommandLineTools
```

From this example directory:

```bash
rustup toolchain install 1.93.1 --profile minimal
uv run --no-project --python 3.12 python check.py --report .sanka/acceptance.json
```

The converter is published as the scoped GitHub prerelease
[`api-converters-v0.1.0a1`](https://github.com/sankaHQ/extensions/releases/tag/api-converters-v0.1.0a1)
from catalog commit `db8953b596325b8ed982c69e92a5a08ad0d3a5d6`, together with its `sanka-ts-capture` and
`sanka-http-replay` dependencies (candidate version 0.1.0a1). The [shared consumer](../../scripts/candidate.py)
(`Published`) checks that the manifest at that commit is byte-identical to the
released asset and that every wheel URL points at the release, then installs through
the public CLI's own marketplace commands pinned to that commit. Published CLI 0.2.12
and Extension SDK 0.1.0a4 run in isolated environments. Wheel SHA-256 values and
resolved CLI dependencies are recorded in the acceptance report. A sibling checkout
is never required. The CLI's default marketplace snapshot predates this release, so
the explicit revision is required.

The harness executes these public commands inside a fresh source copy. `FLAGS`
represents the configuration and explicit toolchain environment forwarding
assembled in `check.py`; `PLAN_HASH` is the reviewed runtime plan hash, not the
extension's separate plan hash:

```bash
sanka extension marketplace add https://github.com/sankaHQ/extensions.git \
  --revision db8953b596325b8ed982c69e92a5a08ad0d3a5d6 --name release --trust --json
sanka extension add sanka/typescript-to-rust --marketplace release --json
sanka scan . --extension-config '{"source_framework":"express","target_framework":"axum","source_file":"src/app.ts"}' --json
sanka plan . --to axum $FLAGS --json
sanka apply --plan-hash "$PLAN_HASH" $FLAGS --json
sanka test $FLAGS --json
sanka verify $FLAGS --json
```

This block explains the owned, temporary lifecycle; run `check.py` to reproduce
its complete installation and exact commands. The report lists those commands.
The harness reviews the generated file list, exactly two routes, no scanner gaps,
the supported launcher and identical repeated plans before passing the exact
runtime hash to apply. It checks each generated file against reviewed plan bytes
and confirms source files were preserved. Generated applications live under
`.sanka/extensions/sanka/typescript-to-rust/rust/` in the disposable consumer copy;
the harness deletes that copy when complete, retaining only the chosen report.
No hand-maintained Rust counterpart is checked in.

## Acceptance contract and limits

A passing report requires independent source compilation/HTTP tests, scan, plan,
apply, generated Rust compilation/tests, extension behavioral replay, actual
source and generated executable HTTP comparison, and unchanged source hashes.
It records generated artifact hashes, both plan hashes, toolchains and release
identity. Any missing toolchain, failed stage or download error fails the command.
Read [evidence.json](evidence.json) for the checked-in execution record.

The extension's `test` uses Rust `tower::ServiceExt::oneshot` probes;
`verify` additionally transpiles and serves the captured Express module over a
Unix socket. This harness also starts the compiled source launcher and the
compiled generated Rust binary on loopback TCP to compare both literal routes.
The temporary directory is not a security sandbox: source and generated code run.

No middleware, dynamic payloads, database/write handlers, deployment or production
cutover is tested. Express case-insensitive and trailing-slash routing, ETag and
X-Powered-By headers are not reproduced. Unknown routes and other HTTP methods
are outside this contract. These explicit gaps are not passing parity evidence.
