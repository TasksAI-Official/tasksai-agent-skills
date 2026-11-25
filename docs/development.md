# Development and release

This public repository is the standalone buyer connector. The merchant service,
paid instruction catalogs, wallets and customer records are maintained separately.
The `0.3.1` release carries the existing `0.3.0` connector behavior with public
packaging, documentation and registry metadata.

```sh
python -m venv .venv
python -m pip install -e . pytest build twine uv
python -m pytest
python -m build
python -m twine check dist/*
python scripts/audit_distribution.py
python scripts/verify_clean_install.py --wheel dist/tasksai_agent_skills-0.3.1-py3-none-any.whl
```

Use the executable inside `.venv` or activate the environment first. The clean
installation check creates another temporary environment, installs the built
wheel, preserves a pre-existing human connection, starts all three real MCP
connections, searches the live catalogs, reads free previews and quotes, and
confirms purchasing is blocked without a policy. It also checks every raw package
URL returns HTTP 402 without exposing instructions. **It makes no paid calls.**

The test matrix runs on Mac, Windows and Linux with Python 3.11 and 3.14. Public
source, wheel and source-distribution audits must pass before publishing. The
release workflow uses short-lived GitHub identity for PyPI and the MCP Registry;
no publisher token belongs in this repository.

The PyPI trusted publisher must be configured for:

| Setting | Value |
| --- | --- |
| Project | `tasksai-agent-skills` |
| GitHub owner | `TasksAI-Official` |
| Repository | `tasksai-agent-skills` |
| Workflow | `release.yml` |
| Environment | `pypi` |

Release tags are `vVERSION`. The workflow tests installation before uploading the
package. It publishes registry metadata only after the PyPI upload succeeds.
GitHub OIDC proves control of `io.github.TasksAI-Official/tasksai-agent-skills`.
The registry entry includes only package and public setup metadata.
