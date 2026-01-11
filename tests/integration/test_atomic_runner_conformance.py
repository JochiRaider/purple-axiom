import os
import pytest


@pytest.mark.integration
def test_atomic_runner_conformance_twice_same_inputs():
    """
    Lab-gated integration harness.

    Enable with:
      PA_ATOMIC_INTEGRATION=1

    Expected (future) behavior once the runner exists:
      - Run the pinned Atomic action twice with identical inputs against the same target_asset_id
      - Assert resolved_inputs_sha256 identical across both runs
      - Assert action_key identical across both runs
      - Assert required runner evidence artifacts exist under runs/<run_id>/runner/actions/<action_id>/

    This test is a placeholder harness; it will be wired to the runner CLI in a later change.
    """
    if os.environ.get("PA_ATOMIC_INTEGRATION") != "1":
        pytest.skip("PA_ATOMIC_INTEGRATION not enabled (lab-gated integration test).")

    runner_cmd = os.environ.get("PA_RUNNER_CMD")
    if not runner_cmd:
        pytest.fail("PA_RUNNER_CMD is required when PA_ATOMIC_INTEGRATION=1 (path/command for Purple Axiom runner).")

    pytest.skip("Runner CLI wiring not yet implemented.")
