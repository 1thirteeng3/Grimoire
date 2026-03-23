"""
Valida o ambiente de desenvolvimento antes do setup.
Executa: python scripts/setup_env.py
"""

import platform
import shutil
import subprocess
import sys


def check(name: str, condition: bool, fix_msg: str) -> bool:
    if condition:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}")
        print(f"    → {fix_msg}")
    return condition


def main() -> None:
    print(f"\nSistema: {platform.system()} {platform.machine()}")
    print("\nVerificando pré-requisitos...\n")
    failures: list[str] = []

    ok = check(
        "Python 3.11+",
        sys.version_info >= (3, 11),
        "Instalar Python 3.11+ em python.org",
    )
    if not ok:
        failures.append("python")

    ok = check("Node.js 20+", shutil.which("node") is not None, "Instalar Node.js 20 LTS em nodejs.org")
    if not ok:
        failures.append("node")

    ok = check("Rust/Cargo", shutil.which("cargo") is not None, "Instalar via rustup.rs")
    if not ok:
        failures.append("cargo")

    ok = check("uv (Python PM)", shutil.which("uv") is not None, "pip install uv")
    if not ok:
        failures.append("uv")

    ok = check("Docker", shutil.which("docker") is not None, "Instalar Docker Desktop em docker.com")
    if not ok:
        failures.append("docker")

    if platform.system() == "Windows":
        try:
            subprocess.run(["cl.exe"], capture_output=True, check=False)
            check("MSVC C++ Build Tools", True, "")
        except FileNotFoundError:
            check(
                "MSVC C++ Build Tools",
                False,
                "Instalar Visual Studio Build Tools (Desktop development with C++)",
            )
            failures.append("msvc")

    if failures:
        print(f"\n✗ {len(failures)} pré-requisito(s) faltando: {', '.join(failures)}")
        print("Resolva os itens acima antes de continuar.\n")
        sys.exit(1)

    print("\n✓ Ambiente validado. Execute: make setup\n")


if __name__ == "__main__":
    main()
