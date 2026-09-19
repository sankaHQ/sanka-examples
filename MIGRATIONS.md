# Migration example contract (v1)

Applications are organized by their **source** framework. Python, TypeScript,
Go, Rust, Swift and Kotlin describe separate source or destination fields; a
supported destination never implies a supported source.

`manifest.json` remains byte-for-byte compatible with its existing v1 consumers.
It retains all existing IDs and fields. `migrations.json` is the companion index
for the new migration walkthroughs; each checked-in entry points to its own
`migration.json`, source, README and acceptance evidence. Planned entries have no
runnable path and must not appear in the runnable application table.
`separately_tracked` records existing cookbook paths with their own acceptance
contracts; it does not claim that they have passed this index's migration/v1 gate.

Each `migration.json` has schema `sanka-examples/migration/v1`, its repository
relative `id`, a `source` object with `language` and `framework`, and a
`destinations` array. Every destination records `language`, `framework`,
`extension_id`, `release_status`, `candidate_revision` and `supported_stages`. The example also records
`license` and `provenance`. Destination stages are an explicit ordered subset of
`scan`, `plan`, `apply`, `test`, `verify`; Compose is limited to scan/plan.
Acceptance evidence must explicitly pass every advertised stage, match the
pinned converter identity, and retain hashes of the unchanged source and generated
files. The validator rejects stale source hashes and failed or missing stages.
Evidence must distinguish source checks, target compilation,
comparison scope, unsupported behavior and stages not run. A stage list is a
capability declaration, not proof that a run passed.

Run `python3 scripts/check_catalog.py` after editing catalog metadata. Source
applications, dependency locks, checks, README, license and metadata belong to
the example directory. Shared installer/catalog/workflow changes have one owner.
Generated applications and full transient reports live under ignored `.sanka/`;
never maintain a second hand-edited target application.

## Consumer audit

Checked on 2026-09-19 before adding entries:

- `sanka-examples/README.md` describes v1. No executable manifest reader exists
  in this repository.
- `sanka/scripts/check_extension_compatibility.py` clones a pinned examples
  revision and runs `extensions/config-upgrade/check.py`; it does not read the
  manifest. `sanka/.github/workflows/publish.yml` invokes that independent gate.
- Searches of maintained `sanka`, `extensions`, `sanka-public`, `bench`, and
  umbrella scripts found no consumer of `sanka-examples/manifest/v1` or this
  repository's manifest path. Other projects' manifests are unrelated.
- External consumers cannot be enumerated from these checkouts. Consequently,
  this change keeps the original manifest unchanged and adds a versioned
  companion rather than widening the v1 schema.

The independent extension developer journey and published Django quickstart
remain separate checks. This change does not change the runtime publication gate
or its fixture pin. Candidate extension publication and human PR approval remain
separate from example acceptance.

## Candidate installation

[`scripts/candidate.py`](scripts/candidate.py) creates a fresh consumer source
copy, CLI environment and extension store for each run. It fetches exactly
`edc6e27744e9a0cb1a8f72cd5bb0f3003288fc20` from the public extensions repository,
checks the selected revision and catalog (an example can select another full
immutable commit with the `revision` argument), builds the selected converter and its
helper packages with constrained build dependencies, and records wheel hashes.
SDK 0.1.0a4 and connector SDK 0.1.0a12 use immutable release URLs and known
SHA-256 digests. CLI 0.2.12 is installed from PyPI; the report records its resolved
dependency versions. The TypeScript bundle is downloaded with the candidate's
pinned tarball and bundle digest verifier.

The helper serves wheels over loopback HTTPS with a temporary certificate trusted
only by the child CLI, builds a temporary marketplace manifest, and executes:

```text
sanka extension marketplace add <temporary-catalog> --name candidate --trust --json
sanka extension add sanka/<selected-converter> --marketplace candidate --json
```

These commands are part of the executable `check.py` walkthrough in each example;
the temporary catalog is not a public marketplace. Wheel hashes, dependency
validation, isolation and plan review stay enabled. Nothing is installed into the
user's CLI or system trust store. Converter source is obtained by immutable public
Git fetch, never by depending on an adjacent checkout.

Setup requires public package/download access. Application checks and migration
replay require no customer data, credentials, Sanka services or inference. CI does
not invoke any live Jev evaluation. Reports fail closed on command errors; missing
platform verification must remain explicit. This is offline application behavior,
not a claim that a cold dependency installation works without a network.
