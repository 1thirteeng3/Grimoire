from app.integrations.obsidian_cli import ObsidianCliError
from app.rag.ingestion import index_obsidian_vault


def test_index_obsidian_vault_success(monkeypatch):
    monkeypatch.setattr("app.rag.ingestion.list_notes", lambda: ["A.md", "B.md"])
    monkeypatch.setattr("app.rag.ingestion.read_note", lambda path: f"conteudo {path}")
    captured = {}

    def _upsert(docs):
        captured["docs"] = docs
        return True

    monkeypatch.setattr("app.rag.ingestion.upsert_documents", _upsert)
    count = index_obsidian_vault(domains=["software_engineering"])
    assert count == 2
    assert captured["docs"][0]["domain"] == "software_engineering"


def test_index_obsidian_vault_returns_zero_when_list_fails(monkeypatch):
    monkeypatch.setattr(
        "app.rag.ingestion.list_notes",
        lambda: (_ for _ in ()).throw(ObsidianCliError("missing cli")),
    )
    assert index_obsidian_vault() == 0


def test_index_obsidian_vault_skips_unreadable_notes(monkeypatch):
    monkeypatch.setattr("app.rag.ingestion.list_notes", lambda: ["ok.md", "bad.md"])

    def _read(path: str):
        if path == "bad.md":
            raise ObsidianCliError("bad")
        return "ok"

    monkeypatch.setattr("app.rag.ingestion.read_note", _read)
    monkeypatch.setattr("app.rag.ingestion.upsert_documents", lambda docs: True)
    assert index_obsidian_vault() == 1
