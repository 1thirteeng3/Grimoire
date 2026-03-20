"""
Inspeciona a API do SDK honcho-ai instalada no ambiente local.
Executar: python scripts/validate_honcho_api.py
"""

import inspect


def validate_honcho_sdk() -> int:
    try:
        import honcho_ai  # type: ignore[import-not-found]
    except ImportError:
        print("ERRO: honcho-ai não instalado. Execute: uv add honcho-ai")
        return 1

    version = getattr(honcho_ai, "__version__", "desconhecida")
    print(f"honcho_ai versão: {version}")

    if hasattr(honcho_ai, "AsyncHoncho"):
        cls = honcho_ai.AsyncHoncho
        print("Classe detectada: AsyncHoncho")
    elif hasattr(honcho_ai, "Honcho"):
        cls = honcho_ai.Honcho
        print("Classe detectada: Honcho")
    else:
        print("Nenhuma classe Honcho detectada no SDK")
        print(f"Atributos disponíveis: {dir(honcho_ai)}")
        return 1

    methods = [name for name in dir(cls) if not name.startswith("_")]
    print(f"Métodos públicos ({len(methods)}): {methods}")
    print(f"Assinatura __init__: {inspect.signature(cls.__init__)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(validate_honcho_sdk())
