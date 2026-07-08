"""Console entry point: run the packaged checks against the archetype repo in cwd.

Usage (from an archetype repo root or its tests/ directory):

    uvx --from git+https://github.com/p6m-archetypes/archetype-test-harness@main archetype-test

Extra arguments are passed straight to pytest, e.g. `archetype-test -m "not build" -v`.

This module deliberately lives OUTSIDE the archetype_harness package: pytest rewrites
a plugin's assert statements at import time, so archetype_harness must not be imported
before pytest.main() starts (find_spec locates it without executing it). Keeping the
entry point separate avoids a PytestAssertRewriteWarning on every run.
"""

import sys
from importlib.util import find_spec
from pathlib import Path

import pytest


def main() -> None:
    # pytest marks every top-level module of a pytest11 distribution for assert
    # rewriting and warns about any that are already imported. This module is the
    # running console script, so it's always imported by the time pytest starts;
    # dropping it from sys.modules avoids the warning (the wrapper's reference to
    # main() keeps these globals alive, and nothing imports this module again).
    sys.modules.pop("archetype_test_cli", None)
    spec = find_spec("archetype_harness")
    checks = Path(spec.submodule_search_locations[0]) / "checks.py"
    sys.exit(pytest.main([str(checks), "-ra", *sys.argv[1:]]))
