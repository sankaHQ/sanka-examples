# blog-posts

A Django REST Framework bulletin board: `Post` with a foreign key to Django's
user model. Seeded with two users and three posts (`db.sqlite3` committed).

```bash
uv tool install --upgrade --python 3.12 'sanka-cli==0.3.9'
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
sanka extension marketplace list
sanka extension marketplace upgrade official
sanka extension add sanka/drf-to-fastapi

sanka scan .
sanka plan . --to python-fastapi --orm sqlalchemy --generation minimal \
  --output .sanka/output/fastapi --strategy native --package-manager uv
# Review .sanka/plan.json and use the hash printed by Plan.
sanka apply --root . --plan-hash '<reviewed-plan-hash>'
sanka test .
sanka verify .
```

Stop before Apply if Plan reports unsupported routes or manual adaptations.
