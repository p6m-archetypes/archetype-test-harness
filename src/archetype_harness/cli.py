"""Console entry point: run the packaged checks against the archetype repo in cwd.

Usage (from an archetype repo root or its tests/ directory):

    uvx --from git+https://github.com/p6m-archetypes/archetype-test-harness@dev archetype-test

Extra arguments are passed straight to pytest, e.g. `archetype-test -m "not build" -v`.
"""

import sys
from importlib.resources import files

import pytest


def main() -> None:
    checks = files("archetype_harness").joinpath("checks.py")
    sys.exit(pytest.main([str(checks), "-ra", *sys.argv[1:]]))
