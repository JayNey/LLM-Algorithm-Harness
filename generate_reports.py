#!/usr/bin/env python3
"""
Thin launcher for report generation.

The implementation lives in examples/generate_reports.py (run-directory
aware: resolves the latest run via results/latest.json and archives
reports under reports/<run-name>/). Usage:

    python3 generate_reports.py [--results-dir DIR] [--output DIR]
"""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).parent / "examples" / "generate_reports.py"), run_name="__main__")
