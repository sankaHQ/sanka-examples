# Sanka Examples

Real, runnable applications for trying [Sanka](https://sanka.com) migrations.
Applications are organized by their source framework. Each walkthrough names
its source and destination separately and states the scope actually verified.
The Django examples include seeded SQLite databases; the extension starter
demonstrates how to build a capability. Neither requires a Sanka account or API token.

The [migration index](migrations.json) and [example contract](MIGRATIONS.md) track
new language paths, converter versions and acceptance evidence. Published
experimental converters install from the public catalog pinned to their release
commit; unpublished candidates use immutable candidate installation instead.

## Published Django quickstart

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first,
then use separate CLI and application environments with Python 3.12:

```bash
uv tool install --python 3.12 sanka-cli
git clone https://github.com/sankaHQ/sanka-examples
cd sanka-examples/django/order-tracker
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
sanka extension add sanka/drf-to-fastapi
sanka scan .
sanka plan . --to fastapi --generation minimal \
  --output .sanka/output/fastapi --strategy native --package-manager uv
```

The CLI discovers the application's `.venv`; it does not need to share that
environment. Review the generated plan before proceeding with apply, test and
verify. Follow the [complete quickstart](https://sanka.com/docs/developers/quickstart/cli/)
for those stages and their generated-environment requirements.

## Build an extension

The [Config upgrade starter](extensions/config-upgrade/) demonstrates packaging,
the typed SDK contract, trusted installation and CLI scan/plan using published
artifacts. Its single acceptance command runs without a runtime checkout or
private services. It is independent of the application migration examples below.

## Classifier conversion candidate

The [LLM classification to Jev cookbook](ai/llm-classification-to-jev/) exercises
an unpublished Sanka Code converter candidate with an explicit reviewed decision
specification, isolated CLI acceptance, and offline compatibility tests. Live
model quality and economics are separate, unverified gates. No provider keys are
needed for the offline walkthrough.

## Apps

| App | Framework | What it exercises |
| --- | --- | --- |
| [django/order-tracker](django/order-tracker/) | Django + DRF | Two related models (FK + `related_name`), unique constraint, choices, decimals — the recommended starting point |
| [django/blog-posts](django/blog-posts/) | Django + DRF | Foreign key to `AUTH_USER_MODEL`, seeded users |
| [django/gadget-inventory](django/gadget-inventory/) | Django + DRF | Exact runnable project used by the Django-to-FastAPI migration guide |
| [django/widget-inventory](django/widget-inventory/) | Django + DRF | Smallest possible app: one model, full CRUD |

## Experimental migration walkthroughs

These are synthetic runnable sources. Each guide pins its converter commit and
records what passed. Generated applications are ignored `.sanka/` artifacts.

| Source example | Source | Destination | Verified migration scope |
| --- | --- | --- | --- |
| [flask/status-api](flask/status-api/) | Python / Flask | Go / Fiber (published `api-converters-v0.1.0a1`) | All five CLI stages; two literal GET routes; native build/tests and live HTTP comparison |
| [express/status-api](express/status-api/) | TypeScript / Express | Rust / axum (published `api-converters-v0.1.0a1`) | All five CLI stages; two literal GET routes; native build/tests and live HTTP comparison |
| [react-native/task-list](react-native/task-list/) | TypeScript / React Native | Swift / SwiftUI (published `mobile-converters-v0.1.0a1`) | All five CLI stages; macOS compilation and five structural action replays |
| Same React Native source | TypeScript / React Native | Kotlin / Compose (published `mobile-converters-v0.1.0a1`) | Scan and plan only; no generated app |

See each example's `evidence.json` and the [companion index](migrations.json).
SwiftUI verification does not establish pixels, layout, accessibility or simulator/
device parity. React Native source checks cover types, an iOS bundle and Metro
startup; execution on a device remains unverified.

The Go, Rust and React Native converters are published as experimental scoped
prereleases. These results do not qualify arbitrary applications or production
cutover.

### Bench-tier corpus (referenced by pin, not vendored)

Real applications adopted as benchmark-corpus candidates. Each entry pins an
upstream commit in `manifest.json` under `tier: "bench"`, with the recorded
`sanka scan` inventory from the corpus sweep that selected it:

| App | License | Endpoints | Pinned ref |
| --- | --- | --- | --- |
| [peering-manager](https://github.com/peering-manager/peering-manager) | Apache-2.0 | 666 | `0829463` |
| [readthedocs.org](https://github.com/readthedocs/readthedocs.org) | MIT | 201 | `edae2d4` |

Behavior-oracle bench tasks for these apps are authored in
[Sanka Migration Bench](https://github.com/sankaHQ/sanka-bench) as the corpus
grows.

`manifest.json` is the machine-readable index (id, framework, tier, features).
Apps tagged `showcase` are small and legible for documentation; the corpus
grows over time with `bench`-tier apps — larger, messier applications that
double as [Sanka Migration Bench](https://github.com/sankaHQ/sanka-bench)
sources.

New source framework directories are added only with runnable applications and
reproduced migration acceptance. A Go or Rust destination does not establish a
Go or Rust source migration. React Native support does not establish arbitrary
React web conversion. The checked-in Python Jev cookbook has its own acceptance and live-evaluation
gates and is tracked separately in `migrations.json`.

## License

Apache-2.0. The applications are synthetic examples maintained by Sanka.
