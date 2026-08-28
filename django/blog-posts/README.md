# blog-posts

A Django REST Framework bulletin board: `Post` with a foreign key to Django's
user model. Seeded with two users and three posts (`db.sqlite3` committed).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt sanka-cli "sqlalchemy[asyncio]" httpx uvicorn

sanka scan .
sanka plan . --to fastapi --orm sqlalchemy
sanka apply --to fastapi
sanka test
sanka verify --to fastapi
```
