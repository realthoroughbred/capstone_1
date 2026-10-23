#!/usr/bin/env python3
"""Explicitly approved, isolated real AWS Config/Lambda demonstration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.sg_demo import main

if __name__ == "__main__":
    raise SystemExit(main())
