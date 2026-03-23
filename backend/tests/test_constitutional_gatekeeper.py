from unittest.mock import patch

import pytest

from app.rag.jit_prompting import DogmasCache, PromptBloatError, compile_constitution


def test_constitution_under_limit_passes(tmp_path):
    del tmp_path
    fake_cache = DogmasCache()
    fake_cache._cache["software_engineering"] = [
        {
            "filepath": "regra1.md",
            "domain": "software_engineering",
            "body": "Nunca usar eval().",
            "tags": ["seguranca"],
        }
    ]
    with patch("app.rag.jit_prompting._cache", fake_cache):
        result = compile_constitution(["software_engineering"])
        assert "eval()" in result


def test_constitution_over_limit_raises_bloat_error(tmp_path):
    del tmp_path
    big_body = "Esta é uma regra muito longa. " * 500
    fake_cache = DogmasCache()
    fake_cache._cache["software_engineering"] = [
        {"filepath": f"regra{i}.md", "domain": "software_engineering", "body": big_body, "tags": []}
        for i in range(10)
    ]
    with patch("app.rag.jit_prompting._cache", fake_cache):
        with pytest.raises(PromptBloatError) as exc:
            compile_constitution(["software_engineering"])
        assert exc.value.current_tokens > exc.value.limit
        assert exc.value.domain == "software_engineering"
