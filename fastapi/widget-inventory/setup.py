# SPDX-License-Identifier: Apache-2.0
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "source"))
from app import engine
from models import Base

Base.metadata.create_all(engine)
