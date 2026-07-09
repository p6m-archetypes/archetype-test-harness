"""The shared archetype checks, collected by pytest via the archetype-test CLI.

Tier 1 (default): render + static checks. Fast, needs only archetect + network/cache.
Tier 2 (-m build): compiles and tests the generated project with its own toolchain.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

BUILD_STEP_TIMEOUT = 900  # seconds per build step

# Anything that looks like an unrendered Jinja/Archetect placeholder. Archetect
# templates in this org are authored with inner padding - `{{ project-name }}`,
# `{% if x %}`, and the whitespace-control forms `{{- x -}}` / `{%- x -%}` - so a
# genuine leak always has a `-`/`+`/`~` control char or whitespace right after the
# opening `{{`. That padding is what distinguishes a real leak from literal
# templating that must survive rendering:
#   - `${{ ... }}` GitHub Actions expressions (excluded via the `$` lookbehind);
#   - docker/metadata-action Go-templates in generated CI workflows, e.g.
#     `enable={{is_default_branch}}`, `value={{version}}`;
#   - Grafana `legendFormat` tokens in generated dashboards, e.g. `{{method}}`,
#     `{{status_code}}`, `{{operation_type}}`.
# Those hug their braces (no adjacent space), so requiring whitespace/control after
# `{{` skips them while still catching unrendered `{{ name }}` placeholders.
UNRENDERED = re.compile(r"(?<!\$)\{\{[-+~]?\s|\{%")


def test_expected_files_exist(case, rendered_project: Path):
    missing = [f for f in case.expected_files if not (rendered_project / f).is_file()]
    assert not missing, f"files missing from rendered project: {missing}"


def test_absent_files_not_rendered(case, rendered_project: Path):
    present = [f for f in case.absent_files if (rendered_project / f).exists()]
    assert not present, f"files rendered that this case must not produce: {present}"


def test_no_unrendered_placeholders_in_paths(rendered_project: Path):
    leaked = [
        str(p.relative_to(rendered_project))
        for p in rendered_project.rglob("*")
        if "{{" in p.name or "{%" in p.name
    ]
    assert not leaked, f"unrendered placeholders in file/dir names: {leaked}"


def test_no_unrendered_placeholders_in_content(rendered_project: Path):
    leaks: list[str] = []
    for path in rendered_project.rglob("*"):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if b"\0" in raw:  # binary file
            continue
        for lineno, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
            if UNRENDERED.search(line):
                leaks.append(f"{path.relative_to(rendered_project)}:{lineno}: {line.strip()}")
    assert not leaks, "unrendered placeholders in file contents:\n" + "\n".join(leaks)


def test_generated_yaml_is_valid(case, rendered_project: Path):
    errors: list[str] = []
    for pattern in case.yaml_globs:
        files = sorted(rendered_project.glob(pattern))
        if not files:
            errors.append(f"glob {pattern!r} matched no files")
            continue
        for path in files:
            rel = path.relative_to(rendered_project)
            try:
                # k8s manifests may hold multiple documents; list() forces a full parse
                docs = list(yaml.safe_load_all(path.read_text()))
            except yaml.YAMLError as exc:
                errors.append(f"{rel}: {exc}")
                continue
            if not any(doc is not None for doc in docs):
                errors.append(f"{rel}: parses but contains no YAML documents")
    assert not errors, "invalid generated YAML:\n" + "\n".join(errors)


@pytest.mark.build
def test_build_steps(case, rendered_project: Path):
    missing = [tool for tool in case.requires if shutil.which(tool) is None]
    if missing:
        pytest.skip(f"required toolchain not on PATH: {missing}")

    env = {**os.environ, **case.env}
    for step in case.build_steps:
        result = subprocess.run(
            step,
            cwd=rendered_project,
            capture_output=True,
            text=True,
            timeout=BUILD_STEP_TIMEOUT,
            env=env,
        )
        assert result.returncode == 0, (
            f"build step {' '.join(step)!r} failed (exit {result.returncode})\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
