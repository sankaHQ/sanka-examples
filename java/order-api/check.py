# SPDX-License-Identifier: Apache-2.0
"""Qualify the pinned Java candidate through the installed public CLI."""

import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLE.parents[1] / "scripts"))
from java_candidate import main

if __name__ == "__main__":
    main(EXAMPLE)
