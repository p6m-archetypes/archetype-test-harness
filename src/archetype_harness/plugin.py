"""Pytest plugin: manifest loading, case parametrization, and the shared render fixture.

Loaded automatically (pytest11 entry point) wherever archetype-test-harness is
installed. Cases come from the archetype repo's tests/manifest.yaml; each case is
rendered once per session and shared by every check.
"""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

RENDER_TIMEOUT = 300  # seconds; includes cloning library sources on a cold cache


@dataclass
class Case:
    name: str
    answers: Path
    project_dir: str
    expected_files: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    build_steps: list[list[str]] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    yaml_globs: list[str] = field(default_factory=list)


def find_tests_dir(start: Path) -> Path:
    """Locate the directory holding manifest.yaml: <start>/tests, <start>, or their parents."""
    for base in (start, *start.parents):
        for candidate in (base / "tests", base):
            if (candidate / "manifest.yaml").is_file() and (candidate / "answers").is_dir():
                return candidate
    raise pytest.UsageError(
        f"no tests/manifest.yaml found at or above {start}; "
        "run from an archetype repo or pass --archetype-dir"
    )


def load_cases(tests_dir: Path) -> list[Case]:
    manifest = yaml.safe_load((tests_dir / "manifest.yaml").read_text())
    return [
        Case(
            name=raw["name"],
            answers=tests_dir / raw["answers"],
            project_dir=raw["project_dir"],
            expected_files=raw.get("expected_files", []),
            requires=raw.get("requires", []),
            build_steps=raw.get("build_steps", []),
            env={k: str(v) for k, v in raw.get("env", {}).items()},
            yaml_globs=raw.get("yaml_globs", []),
        )
        for raw in manifest["cases"]
    ]


def pytest_addoption(parser):
    group = parser.getgroup("archetype-test-harness")
    group.addoption(
        "--archetype-dir",
        default=".",
        help="archetype repo root (or its tests/ dir) containing manifest.yaml; default: cwd",
    )
    group.addoption(
        "--offline",
        action="store_true",
        help="pass --offline to archetect (use only already-cached library sources)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "build: builds the generated project; requires the language toolchain on PATH",
    )


def pytest_generate_tests(metafunc):
    if "case" in metafunc.fixturenames:
        tests_dir = find_tests_dir(Path(metafunc.config.getoption("--archetype-dir")).resolve())
        cases = load_cases(tests_dir)
        metafunc.parametrize("case", cases, ids=[c.name for c in cases], indirect=True, scope="session")


@pytest.fixture(scope="session")
def case(request) -> Case:
    return request.param


@pytest.fixture(scope="session")
def rendered_project(case: Case, tmp_path_factory, request) -> Path:
    """Render the archetype headlessly for this case; returns the generated project dir."""
    if shutil.which("archetect") is None:
        pytest.fail(
            "archetect not found on PATH. Install it first: https://archetect.github.io/ "
            "(brew install archetect-cli or download a release binary)."
        )

    tests_dir = find_tests_dir(Path(request.config.getoption("--archetype-dir")).resolve())
    archetype_root = tests_dir.parent if tests_dir.name == "tests" else tests_dir

    out_dir = tmp_path_factory.mktemp(f"render-{case.name}")
    cmd = [
        "archetect", "render", str(archetype_root),
        "--dest", str(out_dir),
        "-A", str(case.answers),
        "-D",  # use prompt defaults for anything the answers file doesn't cover
        "--headless",
    ]
    if request.config.getoption("--offline"):
        cmd.append("--offline")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=RENDER_TIMEOUT)
    if result.returncode != 0:
        pytest.fail(
            f"archetect render failed (exit {result.returncode})\n"
            f"command: {' '.join(cmd)}\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )

    project = out_dir / case.project_dir
    if not project.is_dir():
        rendered = [p.name for p in out_dir.iterdir()]
        pytest.fail(
            f"render succeeded but expected project dir {case.project_dir!r} is missing; "
            f"rendered top-level entries: {rendered}"
        )
    return project
