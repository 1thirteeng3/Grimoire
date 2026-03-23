from app.core.entity_loader import load_and_validate_entities

import pytest


def test_invalid_yaml_aborts_boot(tmp_path):
    invalid_yaml = tmp_path / "bad_entity.yaml"
    invalid_yaml.write_text(
        """
entity_id: test
name: Entidade Corrompida
priority: 'nao_e_numero'
tier_lock: 1
bind_domains: [software]
critic_constitution:
  bind_domains: [software]
""",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc_info:
        load_and_validate_entities(tmp_path)
    assert exc_info.value.code == 1


def test_valid_yaml_loads_successfully(tmp_path):
    valid_yaml = tmp_path / "good_entity.yaml"
    valid_yaml.write_text(
        """
entity_id: belial-001
name: Belial, O Engenheiro
priority: 50
tier_lock: 1
bind_domains: [software_engineering]
critic_constitution:
  bind_domains: [software_engineering]
  required_tags: [seguranca]
""",
        encoding="utf-8",
    )
    entities = load_and_validate_entities(tmp_path)
    assert "belial-001" in entities
    assert entities["belial-001"].priority == 50


def test_mixed_valid_and_invalid_aborts(tmp_path):
    (tmp_path / "good.yaml").write_text(
        "entity_id: ok\n"
        "name: OK\n"
        "priority: 10\n"
        "tier_lock: 1\n"
        "bind_domains: [x]\n"
        "critic_constitution:\n"
        "  bind_domains: [x]\n",
        encoding="utf-8",
    )
    (tmp_path / "bad.yaml").write_text(
        "entity_id: bad\npriority: 'string_invalido'\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        load_and_validate_entities(tmp_path)


def test_empty_directory_loads_default_copilot(tmp_path):
    entities = load_and_validate_entities(tmp_path)
    assert "copilot-introspector" in entities
