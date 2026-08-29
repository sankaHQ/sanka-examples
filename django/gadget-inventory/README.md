# gadget-inventory

The exact Django REST Framework project used by Sanka's
[Django-to-FastAPI migration guide](https://sanka.com/docs/developers/migrate/django-to-fastapi/).
It exposes one `Gadget` model through a DRF `ModelViewSet`, including the
validation and fields shown in the article. A seeded `db.sqlite3` is committed.

This quick start requires [uv](https://docs.astral.sh/uv/) and Python 3.12 or
newer. `uv` downloads Python 3.12 automatically when needed.

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt sanka-cli

sanka scan .
sanka plan . --to fastapi
sanka apply --to fastapi
sanka test
sanka verify --to fastapi
```
