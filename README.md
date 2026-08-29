# Sanka Examples

Real, runnable applications for trying [Sanka](https://sanka.com) migrations.
Every app ships with a seeded SQLite database, so the migration lifecycle works
seconds after cloning — no accounts, no API tokens.

```bash
git clone https://github.com/sankaHQ/sanka-examples
cd sanka-examples/django/order-tracker
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt sanka-cli "sqlalchemy[asyncio]" httpx uvicorn

sanka scan .
sanka plan . --to fastapi --orm sqlalchemy
sanka apply --to fastapi
sanka test
sanka verify --to fastapi
```

Install `sanka-cli` inside the app's virtualenv — the scanner imports the
project's Django code, so tool and app must share an environment.

## Apps

| App | Framework | What it exercises |
| --- | --- | --- |
| [django/order-tracker](django/order-tracker/) | Django + DRF | Two related models (FK + `related_name`), unique constraint, choices, decimals — the recommended starting point |
| [django/blog-posts](django/blog-posts/) | Django + DRF | Foreign key to `AUTH_USER_MODEL`, seeded users |
| [django/gadget-inventory](django/gadget-inventory/) | Django + DRF | Exact runnable project used by the Django-to-FastAPI migration guide |
| [django/widget-inventory](django/widget-inventory/) | Django + DRF | Smallest possible app: one model, full CRUD |

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

New framework directories appear when the Sanka engine gains that migration
lane; today's lane is Django REST Framework → FastAPI.

## License

Apache-2.0. The applications are synthetic examples maintained by Sanka.
