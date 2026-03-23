from app.rag.shadowing import (
    COSINE_THRESHOLD,
    JACCARD_THRESHOLD,
    apply_shadow_xml,
    check_shadow,
    has_dangerous_command,
    process_chunk_against_dogmas,
)


def test_conflito_porta_detectado():
    rag = "Use porta 80. Porta 80 habilita trafego HTTP no nginx."
    dogma = "PROIBIDO: porta 80 em produção. Porta 80 deve ser bloqueada e usar 443."
    result = check_shadow(rag, dogma)
    assert result.should_shadow is True
    assert any("80" in entity for entity in result.matched_entities)
    assert result.jaccard_score >= JACCARD_THRESHOLD
    assert result.cosine_sim >= COSINE_THRESHOLD


def test_port_and_porta_are_canonicalized():
    rag = "Open port 80 for ingress"
    dogma = "Nunca abrir porta 80 sem TLS"
    result = check_shadow(rag, dogma)
    assert result.should_shadow is True


def test_sem_entidades_compartilhadas_nao_faz_shadow():
    rag = "Use Redis para cache de sessoes."
    dogma = "Nunca usar eval() em código Python."
    result = check_shadow(rag, dogma)
    assert result.should_shadow is False
    assert result.reason == "sem entidades compartilhadas"


def test_jaccard_baixo_nao_faz_shadow():
    rag = "PORTA=8080 para métricas"
    dogma = "Nunca abrir porta 80 sem TLS"
    result = check_shadow(rag, dogma)
    assert result.jaccard_score < JACCARD_THRESHOLD
    assert result.should_shadow is False


def test_shadow_xml_contem_warning():
    xml = apply_shadow_xml("use porta 80", "nginx_docs.md", "PROIBIDO porta 80", 0.85)
    assert "<shadowed_text" in xml
    assert "CONFLITO COM DOGMA CRÍTICO" in xml
    assert "use porta 80" in xml


def test_chunk_sem_conflito_retorna_intacto():
    xml = process_chunk_against_dogmas("Use Redis para cache", "redis_docs.md", 0.7, [])
    assert "<shadowed_text" not in xml
    assert "Use Redis para cache" in xml


def test_detecta_rm_rf():
    assert has_dangerous_command("rm -rf /tmp/data") is True


def test_detecta_eval():
    assert has_dangerous_command("result = eval(user_input)") is True


def test_codigo_seguro_nao_detectado():
    assert has_dangerous_command("print(os.getcwd())") is False


def test_detecta_subprocess():
    assert has_dangerous_command('subprocess.run(["ls"])') is True
