# widget-inventory

The smallest useful example: one `Widget` model behind a DRF `ModelViewSet` —
list, create, partial update, validation, delete. Seeded `db.sqlite3`
committed.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt sanka-cli "sqlalchemy[asyncio]" httpx uvicorn

sanka scan .
sanka plan . --to fastapi --orm sqlalchemy
sanka apply --to fastapi
sanka test
sanka verify --to fastapi
```
