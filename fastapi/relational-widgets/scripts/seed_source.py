# SPDX-License-Identifier: Apache-2.0
"""Apply the checked-in Alembic revisions and seed a disposable source schema."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

import psycopg
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

source = Path(sys.argv[1]).resolve()
dsn = os.environ["DATABASE_URL"]
engine = create_engine(dsn.replace("postgresql://", "postgresql+psycopg://", 1))
try:
    with (
        engine.begin() as connection,
        Operations.context(MigrationContext.configure(connection)),
    ):
        for revision in sorted((source / "alembic/versions").glob("*.py")):
            runpy.run_path(str(revision))["upgrade"]()
finally:
    engine.dispose()

with psycopg.connect(dsn, autocommit=True) as connection:
    connection.execute(
        "INSERT INTO parents(id,name,count,enabled,note) VALUES "
        "(4,'alpha',0,false,NULL),(9,'beta',3,true,'original')"
    )
    connection.execute(
        "INSERT INTO widgets(id,name,parent_id,enabled,note) VALUES "
        "(15,'first',4,true,NULL),(23,'second',4,false,'old'),"
        "(27,'third',9,true,'other')"
    )
    connection.execute("SELECT setval('parents_id_seq',41,true)")
    connection.execute("SELECT setval('widgets_id_seq',36,true)")
    connection.execute("CREATE TABLE alembic_version(version_num text NOT NULL)")
    connection.execute("INSERT INTO alembic_version VALUES ('0002')")
