"""The CI definition is code, so it gets a test.

None of the workflow's jobs ran on this machine: the pipeline is hosted, and a
green laptop suite says nothing about whether ``e2e`` starts a backend before it
starts the app it drives. That gap used to be closed by reading the YAML and
hoping. This module closes it mechanically, on every push, before the hosted
run is the first thing that ever parses the file.

It checks the things that silently rot:

* the job graph — ``gate`` must need every job, with ``if: always()``, or a
  failed job shows up as a skipped dependency and the required check passes;
* that the audit and E2E jobs actually start what they claim to (a backend on
  :8000, a preview on :4173) instead of sweeping a login page;
* that every path a ``run`` step mentions still exists in the checkout;
* that the npm/pytest commands they call are real scripts/suites;
* that runner images stay pinned, because ``ubuntu-latest`` moving a major
  version is how a browser disappears from a job overnight.

It deliberately does not try to be a workflow linter. It asserts the promises
this repository's docs make about the gate (docs/CI.md), which is the part a
reader would otherwise have to verify by eye.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT.parent / ".github" / "workflows" / "tests.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert WORKFLOW_PATH.is_file(), f"missing workflow at {WORKFLOW_PATH}"
    # PyYAML resolves the bare `on:` key to the boolean True, so the trigger map
    # has to be read back under either name.
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _jobs(workflow: dict) -> dict:
    return workflow["jobs"]


def _steps(job: dict) -> list[dict]:
    return job.get("steps", [])


def _run_text(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in _steps(job))


def _uses(job: dict) -> list[str]:
    return [str(step["uses"]) for step in _steps(job) if "uses" in step]


def test_every_job_exists_and_is_pinned(workflow: dict) -> None:
    jobs = _jobs(workflow)
    assert set(jobs) == {
        "backend",
        "frontend",
        "ui-audit",
        "e2e",
        "sources",
        "dataset",
        "gate",
    }
    for name, job in jobs.items():
        assert job["runs-on"].startswith("ubuntu-"), f"{name} lost its pinned runner"
        assert not job["runs-on"].endswith("latest"), (
            f"{name} runs on a moving image; pin the version so a browser or Python "
            "upgrade is a deliberate change"
        )


def test_gate_requires_every_job_and_fails_on_a_skipped_one(workflow: dict) -> None:
    gate = _jobs(workflow)["gate"]
    assert set(gate["needs"]) == {
        "backend",
        "frontend",
        "ui-audit",
        "e2e",
        "sources",
        "dataset",
    }
    assert gate.get("if") == "always()", (
        "without `if: always()` a failed job turns the gate into a skipped job, "
        "which branch protection reads as neutral rather than red"
    )
    # The gate must name each dependency's result, or a job could be added to
    # `needs` and never consulted.
    script = _run_text(gate)
    for job in ("backend", "frontend", "ui-audit", "e2e", "sources", "dataset"):
        assert f"needs.{job}.result" in script, f"gate does not inspect {job}"


def test_workflow_runs_on_pushes_and_pull_requests(workflow: dict) -> None:
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["push"]["branches"] == ["main"]
    assert "pull_request" in triggers
    assert "workflow_dispatch" in triggers


def test_audit_job_starts_a_backend_and_requires_sign_in(workflow: dict) -> None:
    audit = _jobs(workflow)["ui-audit"]
    run = _run_text(audit)
    assert "uvicorn backend.api_server:app" in run
    assert "127.0.0.1:8000/health" in run, "the job must wait on /health, not on a port"
    assert "node scripts/ui-audit.cjs --require-sign-in" in run, (
        "the audit falls back to the public pages without --require-sign-in; CI "
        "must treat that fallback as a failure"
    )
    assert "vite preview" in run or "ui-audit.cjs" in run


def test_e2e_job_builds_serves_and_points_the_journey_at_that_server(workflow: dict) -> None:
    e2e = _jobs(workflow)["e2e"]
    run = _run_text(e2e)
    assert "npm run build" in run, "the journey must test the built bundle"
    assert "vite.js preview" in run or "vite preview" in run
    assert "127.0.0.1:4173" in run
    assert (
        "node scripts/e2e-save-visit.cjs --base-url http://127.0.0.1:4173" in run
    ), "without --base-url the journey starts its own servers and tests something else"
    assert "google-chrome" in run, "playwright-core needs a named browser binary"


def test_sources_job_verifies_citations_without_needing_egress(workflow: dict) -> None:
    job = _jobs(workflow)["sources"]
    run = _run_text(job)
    assert "scripts/verify_sources.py" in run
    assert "--network" not in run, (
        "a publisher blocking a runner would fail the gate for no clinical reason; "
        "the live check is a local make target"
    )


def test_dataset_job_rebuilds_and_fails_on_drift(workflow: dict) -> None:
    """The provenance job must rebuild and compare, not merely lint the CSV."""
    job = _jobs(workflow)["dataset"]
    run = _run_text(job)
    assert "python scripts/import_uci_heart.py --check" in run
    assert "--check" in run, "without --check the importer would rewrite the file instead"
    # Standard library only: a pip install here would be a dependency the check
    # does not need, and one more thing that can fail for the wrong reason.
    assert "pip install" not in run
    assert not _uses(job) or all("setup-python" in action or "checkout" in action for action in _uses(job))


def test_job_timeouts_are_bounded(workflow: dict) -> None:
    # A wedged browser or a server that never binds should not consume the
    # six-hour default; the jobs that do real I/O started one each on purpose.
    for name in ("ui-audit", "e2e", "dataset"):
        limit = _jobs(workflow)[name].get("timeout-minutes")
        assert isinstance(limit, int) and 0 < limit <= 40, f"{name} timeout is {limit}"


def test_actions_are_pinned_to_a_major_version(workflow: dict) -> None:
    for name, job in _jobs(workflow).items():
        for action in _uses(job):
            assert re.match(r"^[a-z0-9-]+/[a-z0-9-]+@v\d+$", action), (
                f"{name} uses an unpinned or local action: {action}"
            )


def test_run_steps_only_reference_paths_that_exist(workflow: dict) -> None:
    """A renamed script must fail here, not on the runner after 20 minutes."""
    referenced = set()
    for job in _jobs(workflow).values():
        for match in re.finditer(r"\b(?:scripts|frontend|backend)/[\w./-]+", _run_text(job)):
            referenced.add(match.group(0).rstrip("."))
    assert referenced, "the workflow no longer runs any repository path — check the regex"
    for relative in sorted(referenced):
        # Logs are produced by the job, not checked in; only repository inputs
        # can be required to exist before the runner starts.
        if relative.endswith((".log", ".json")):
            continue
        assert (ROOT / relative).exists(), f"workflow references {relative}, which does not exist"


def test_working_directories_exist_and_npm_scripts_are_real(workflow: dict) -> None:
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    scripts = package["scripts"]
    for name, job in _jobs(workflow).items():
        working = job.get("defaults", {}).get("run", {}).get("working-directory")
        if working:
            assert (ROOT.parent / working).is_dir(), f"{name} works in a missing directory"
        for step in _steps(job):
            directory = step.get("working-directory", working)
            if directory:
                assert (ROOT.parent / directory).is_dir(), (
                    f"{name} step '{step.get('name')}' runs in missing {directory}"
                )
            run = str(step.get("run", ""))
            for command in re.findall(r"npm run ([\w:-]+)", run):
                assert command in scripts, f"{name} runs `npm run {command}`, which is not a script"
                # The script itself must resolve to a file, not a nested npm call
                # to something that was deleted.
                for target in re.findall(r"node (\.\./[\w./-]+)", scripts[command]):
                    assert (ROOT / "frontend" / target).resolve().is_file(), (
                        f"npm script {command} points at missing {target}"
                    )


def test_backend_job_runs_pytest_and_the_script_checks(workflow: dict) -> None:
    run = _run_text(_jobs(workflow)["backend"])
    assert "python -m pytest backend -q" in run
    # The legacy script checks are driven by a loop; the list must still name
    # the clinical assertions, and the loop must run them from the repo.
    assert "test_orchestrator test_nlp_agent" in run
    assert 'python "backend/$test.py"' in run
