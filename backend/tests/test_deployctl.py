import importlib.util
import sys
from pathlib import Path


def _load_deployctl():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "ops" / "deploy" / "deployctl.py"
    spec = importlib.util.spec_from_file_location("deployctl_test_module", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_env_mirror_and_blue_green_release(tmp_path):
    deployctl = _load_deployctl()
    deployctl.ENV_DIR = tmp_path / "env"
    deployctl.STATE_DIR = tmp_path / "state"
    deployctl.ENV_DIR.mkdir(parents=True, exist_ok=True)
    (deployctl.ENV_DIR / "staging.env").write_text("A=1\nB=2\n", encoding="utf-8")
    (deployctl.ENV_DIR / "production.env").write_text("A=3\nB=4\n", encoding="utf-8")

    assert deployctl.command_validate_env_mirror() == 0

    args = deployctl.ReleaseArgs(
        environment="staging",
        version="v1.0.0",
        strategy="blue-green",
        canary_weight=10,
        promote=False,
        dry_run=True,
    )
    assert deployctl.command_release(args) == 0
    state = deployctl._load_state("staging")
    assert state["stable_version"] == "v1.0.0"
    assert state["active_color"] == "green"


def test_canary_release_and_rollback_auto(tmp_path):
    deployctl = _load_deployctl()
    deployctl.STATE_DIR = tmp_path / "state"

    args = deployctl.ReleaseArgs(
        environment="production",
        version="v2.0.0",
        strategy="canary",
        canary_weight=20,
        promote=False,
        dry_run=True,
    )
    assert deployctl.command_release(args) == 0
    state = deployctl._load_state("production")
    assert state["canary_version"] == "v2.0.0"
    assert state["canary_weight"] == 20

    assert (
        deployctl.command_rollback(
            environment="production",
            strategy="auto",
            to_version=None,
            dry_run=True,
        )
        == 0
    )
    rolled = deployctl._load_state("production")
    assert rolled["canary_version"] is None
    assert rolled["canary_weight"] == 0
