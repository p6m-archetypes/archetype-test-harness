# archetype-test-harness

Shared integration test harness for [p6m-archetypes](https://github.com/p6m-archetypes)
archetypes. It renders an archetype headlessly with a known answers file, verifies the
generated project, and builds it with its own toolchain:

- **Render tier** (default, fast; needs only [archetect](https://archetect.github.io/)):
  expected files exist; no unrendered `{{ placeholder }}` tokens in file names or
  contents (GitHub Actions `${{ }}` expressions excluded); declared YAML globs parse
  as valid multi-document YAML, with empty globs failing loudly.
- **Build tier** (`-m build`): runs the manifest's `build_steps` (e.g. `dotnet build`,
  `mvn verify`, `cargo build`) inside the generated project; skips with a notice when
  the required toolchain is not on PATH.

The harness is language-agnostic: everything stack-specific lives in the consuming
repo's manifest.

## Using it from an archetype repo

An archetype repo needs only two things - no Python code:

```
tests/
  manifest.yaml        # test cases: answers file, expected files, yaml globs, build steps
  answers/default.yaml # headless answers for archetect render -A
```

Run from the archetype repo root (or its `tests/` directory):

```sh
# in the flat org checkout, against the sibling harness:
uvx --from ../archetype-test-harness archetype-test

# anywhere, against the published harness:
uvx --from git+https://github.com/p6m-archetypes/archetype-test-harness@dev archetype-test
```

Extra arguments pass through to pytest:

```sh
archetype-test -m "not build"    # fast tier only, no toolchain needed
archetype-test --offline         # use archetect's cached library sources
archetype-test -v --junitxml=results.xml
```

Prerequisites: `archetect` >= 3.0 and `uv` on PATH; SSH or HTTPS access to the
composed library repos on first render (archetect caches them afterwards).

### manifest.yaml schema

```yaml
cases:
  - name: default                 # unique case id, shows up in test names
    answers: answers/default.yaml # passed to archetect render -A (prompt keys are snake_case)
    project_dir: inventory-service # directory the render must produce
    expected_files:               # relative to project_dir, must exist
      - InventoryService.sln
    yaml_globs:                   # must parse as YAML; a glob matching nothing fails
      - ".platform/kubernetes/**/*.yaml"
    requires: [dotnet]            # executables needed by build_steps; missing -> skip
    build_steps:                  # run sequentially inside project_dir
      - [dotnet, build, --nologo]
      - [dotnet, test, --nologo]
    env:                          # extra environment for build_steps
      DOTNET_ROLL_FORWARD: Major
```

Anything the answers file omits falls back to the prompt's default
(`archetect render -D`). Rendered output lands in pytest temp dirs
(`/tmp/pytest-of-<user>/pytest-<N>/render-<case>/`, last 3 runs kept).

## CI

Consumers call the reusable workflow - the entire consumer workflow is:

```yaml
name: Test Archetype
on: [pull_request, push, workflow_dispatch]
jobs:
  test:
    uses: p6m-archetypes/archetype-test-harness/.github/workflows/archetype-test.yaml@dev
    with:
      toolchain: dotnet
      toolchain-version: "9.0.x"
    secrets: inherit
```

The reusable workflow installs archetect (checksum-verified), rewrites the
libraries' `git@github.com:` sources to token-authenticated HTTPS (preferring the
`ARCHETYPE_LIBS_TOKEN` org secret, falling back to `GITHUB_TOKEN`), sets up the
requested toolchain, runs the harness, and uploads the rendered project as an
artifact on failure.

Note: for other repos' workflows to use this repo (both the reusable workflow and
`uvx --from git+...`), this repo must grant org-wide Actions access:
Settings -> Actions -> General -> Access -> "Accessible from repositories in the
organization".

## Development

```sh
uv run archetype-test --archetype-dir ../dotnet-service-basic-archetype  # run against a consumer
uv build                                                                  # sanity-check packaging
```

The package is a pytest plugin (`archetype_harness.plugin`, auto-loaded via the
`pytest11` entry point) plus packaged checks (`archetype_harness/checks.py`) and the
`archetype-test` console script that wires them together.
