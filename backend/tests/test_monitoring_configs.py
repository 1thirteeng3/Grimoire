from pathlib import Path

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_prometheus_and_alertmanager_configs_are_valid_yaml():
    root = _repo_root()
    prometheus_cfg = root / "ops/monitoring/prometheus.yml"
    alertmanager_cfg = root / "ops/monitoring/alertmanager.yml"
    rules_cfg = root / "ops/monitoring/alert_rules.yml"
    slo_cfg = root / "ops/monitoring/slo.yml"

    for path in [prometheus_cfg, alertmanager_cfg, rules_cfg, slo_cfg]:
        assert path.exists(), f"arquivo ausente: {path}"
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        assert isinstance(data, dict), f"yaml invalido: {path}"


def test_required_operational_alerts_are_present():
    root = _repo_root()
    rules_cfg = root / "ops/monitoring/alert_rules.yml"
    with rules_cfg.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    groups = data.get("groups", [])
    rules = [rule for group in groups for rule in group.get("rules", [])]
    names = {rule.get("alert") for rule in rules}

    assert "GrimoireLLMProviderTimeoutHigh" in names
    assert "GrimoirePromptBloatRecurring" in names
    assert "GrimoireRAGAverageLatencyHigh" in names
    assert "GrimoireLLMAverageLatencyHigh" in names
    assert "GrimoireAvailabilitySLOWarning" in names
    assert "GrimoireAvailabilitySLOCritical" in names


def test_operational_runbooks_exist():
    root = _repo_root()
    runbooks = [
        root / "ops/runbooks/README.md",
        root / "ops/runbooks/incident-availability.md",
        root / "ops/runbooks/incident-llm-timeout.md",
        root / "ops/runbooks/incident-prompt-bloat.md",
        root / "ops/runbooks/incident-rag-degradation.md",
    ]
    for path in runbooks:
        assert path.exists(), f"runbook ausente: {path}"
