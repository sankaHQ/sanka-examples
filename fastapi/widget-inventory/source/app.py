# SPDX-License-Identifier: Apache-2.0
from os import environ

from models import Widget
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from fastapi import FastAPI, HTTPException

engine = create_engine(environ["DATABASE_URL"])
app = FastAPI()


@app.post("/widgets", status_code=201)
def create_widget(data: dict):
    if (
        (type(data) is not dict)
        or (set(data) - {"name", "count", "enabled", "note"})
        or ("name" not in data)
        or (type(data["name"]) is not str)
        or ("count" not in data)
        or (
            type(data["count"]) is not int
            or not -2147483648 <= data["count"] <= 2147483647
        )
        or ("enabled" not in data)
        or (type(data["enabled"]) is not bool)
        or (
            "note" in data
            and (data["note"] is not None and (type(data["note"]) is not str))
        )
    ):
        raise HTTPException(status_code=400, detail="invalid request body")
    with Session(engine) as session:
        item = Widget(
            name=data["name"],
            count=data["count"],
            enabled=data["enabled"],
            note=data.get("note"),
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return {
            "id": item.id,
            "name": item.name,
            "count": item.count,
            "enabled": item.enabled,
            "note": item.note,
        }


@app.patch("/widgets/{id}")
def patch_widget(id: int, data: dict):
    if (
        (type(data) is not dict)
        or (set(data) - {"name", "count", "enabled", "note"})
        or ("name" in data and (type(data["name"]) is not str))
        or (
            "count" in data
            and (
                type(data["count"]) is not int
                or not -2147483648 <= data["count"] <= 2147483647
            )
        )
        or ("enabled" in data and (type(data["enabled"]) is not bool))
        or (
            "note" in data
            and (data["note"] is not None and (type(data["note"]) is not str))
        )
    ):
        raise HTTPException(status_code=400, detail="invalid request body")
    with Session(engine) as session:
        item = session.get(Widget, id)
        if item is None:
            raise HTTPException(status_code=404, detail="not found")
        if "name" in data:
            item.name = data["name"]
        if "count" in data:
            item.count = data["count"]
        if "enabled" in data:
            item.enabled = data["enabled"]
        if "note" in data:
            item.note = data["note"]
        session.commit()
        session.refresh(item)
        return {
            "id": item.id,
            "name": item.name,
            "count": item.count,
            "enabled": item.enabled,
            "note": item.note,
        }


@app.put("/widgets/{id}")
def replace_widget(id: int, data: dict):
    if (
        (type(data) is not dict)
        or (set(data) - {"name", "count", "enabled", "note"})
        or ("name" not in data)
        or (type(data["name"]) is not str)
        or ("count" not in data)
        or (
            type(data["count"]) is not int
            or not -2147483648 <= data["count"] <= 2147483647
        )
        or ("enabled" not in data)
        or (type(data["enabled"]) is not bool)
        or (
            "note" in data
            and (data["note"] is not None and (type(data["note"]) is not str))
        )
    ):
        raise HTTPException(status_code=400, detail="invalid request body")
    with Session(engine) as session:
        item = session.get(Widget, id)
        if item is None:
            raise HTTPException(status_code=404, detail="not found")
        item.name = data["name"]
        item.count = data["count"]
        item.enabled = data["enabled"]
        item.note = data.get("note")
        session.commit()
        session.refresh(item)
        return {
            "id": item.id,
            "name": item.name,
            "count": item.count,
            "enabled": item.enabled,
            "note": item.note,
        }


@app.delete("/widgets/{id}", status_code=204)
def delete_widget(id: int):
    with Session(engine) as session:
        item = session.get(Widget, id)
        if item is None:
            raise HTTPException(status_code=404, detail="not found")
        session.delete(item)
        session.commit()
