#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
ENV_DIR = ROOT / "ops" / "deploy" / "environments"
STATE_DIR = ROOT / "ops" / "deploy" / "state"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise RuntimeError(f"Arquivo de ambiente ausente: {path}")
    parsed: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError(f"Linha inválida em {path}: {line}")
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _default_state(environment: str) -> dict[str, Any]:
    return {
        "environment": environment,
        "active_color": "blue",
        "stable_version": None,
        "previous_stable_version": None,
        "canary_version": None,
        "canary_weight": 0,
        "updated_at": _utc_now(),
    }


def _state_path(environment: str) -> Path:
    return STATE_DIR / f"{environment}.json"


def _load_state(environment: str) -> dict[str, Any]:
    path = _state_path(environment)
    if not path.exists():
        return _default_state(environment)
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(environment: str, state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _utc_now()
    _state_path(environment).write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _other_color(color: str) -> str:
    return "green" if color == "blue" else "blue"


def _run_deploy_hook(
    *,
    env_name: str,
    slot: str,
    version: str,
    phase: str,
    dry_run: bool,
) -> None:
    template = os.getenv("RELEASE_DEPLOY_HOOK", "").strip()
    command = ""
    if template:
        command = template.format(env=env_name, slot=slot, version=version, phase=phase)
    if not command:
        print(f"[hook] no-op phase={phase} env={env_name} slot={slot} version={version}")
        return
    if dry_run:
        print(f"[hook] dry-run: {command}")
        return
    subprocess.run(command, shell=True, check=True)


def _run_healthcheck(*, env_name: str, slot: str, version: str, dry_run: bool) -> None:
    template = os.getenv("RELEASE_HEALTHCHECK_URL", "").strip()
    if not template:
        print(f"[health] no-op env={env_name} slot={slot} version={version}")
        return
    url = template.format(env=env_name, slot=slot, version=version)
    if dry_run:
        print(f"[health] dry-run GET {url}")
        return
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=20) as response:
            code = int(getattr(response, "status", 0) or 0)
    except URLError as exc:  # pragma: no cover - runtime external dependency
        raise RuntimeError(f"Healthcheck falhou para {url}: {exc}") from exc
    if code < 200 or code >= 300:
        raise RuntimeError(f"Healthcheck retornou status não-2xx para {url}: {code}")


@dataclass(frozen=True)
class ReleaseArgs:
    environment: str
    version: str
    strategy: str
    canary_weight: int
    promote: bool
    dry_run: bool


def _release_blue_green(state: dict[str, Any], args: ReleaseArgs) -> dict[str, Any]:
    active_color = str(state.get("active_color", "blue"))
    target_color = _other_color(active_color)
    _run_deploy_hook(
        env_name=args.environment,
        slot=target_color,
        version=args.version,
        phase="deploy",
        dry_run=args.dry_run,
    )
    _run_healthcheck(
        env_name=args.environment,
        slot=target_color,
        version=args.version,
        dry_run=args.dry_run,
    )
    state["previous_stable_version"] = state.get("stable_version")
    state["stable_version"] = args.version
    state["active_color"] = target_color
    state["canary_version"] = None
    state["canary_weight"] = 0
    return state


def _release_canary(state: dict[str, Any], args: ReleaseArgs) -> dict[str, Any]:
    active_color = str(state.get("active_color", "blue"))
    canary_color = _other_color(active_color)
    _run_deploy_hook(
        env_name=args.environment,
        slot=canary_color,
        version=args.version,
        phase="canary-deploy",
        dry_run=args.dry_run,
    )
    _run_healthcheck(
        env_name=args.environment,
        slot=canary_color,
        version=args.version,
        dry_run=args.dry_run,
    )
    state["canary_version"] = args.version
    state["canary_weight"] = max(1, min(50, int(args.canary_weight)))
    if args.promote:
        state["previous_stable_version"] = state.get("stable_version")
        state["stable_version"] = args.version
        state["active_color"] = canary_color
        state["canary_version"] = None
        state["canary_weight"] = 0
    return state


def command_release(args: ReleaseArgs) -> int:
    state = _load_state(args.environment)
    if args.strategy == "blue-green":
        state = _release_blue_green(state, args)
    elif args.strategy == "canary":
        state = _release_canary(state, args)
    else:
        raise RuntimeError(f"Estratégia inválida: {args.strategy}")
    _save_state(args.environment, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def command_rollback(
    *,
    environment: str,
    strategy: str,
    to_version: str | None,
    dry_run: bool,
) -> int:
    state = _load_state(environment)
    active_color = str(state.get("active_color", "blue"))
    rollback_strategy = strategy
    if rollback_strategy == "auto":
        rollback_strategy = "canary" if state.get("canary_version") else "blue-green"

    if rollback_strategy == "canary":
        state["canary_version"] = None
        state["canary_weight"] = 0
        _save_state(environment, state)
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    previous = to_version or state.get("previous_stable_version")
    if not previous:
        raise RuntimeError("Rollback blue/green sem versão anterior registrada.")
    target_color = _other_color(active_color)
    _run_deploy_hook(
        env_name=environment,
        slot=target_color,
        version=str(previous),
        phase="rollback",
        dry_run=dry_run,
    )
    _run_healthcheck(env_name=environment, slot=target_color, version=str(previous), dry_run=dry_run)
    state["stable_version"] = str(previous)
    state["active_color"] = target_color
    state["canary_version"] = None
    state["canary_weight"] = 0
    _save_state(environment, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def command_validate_env_mirror() -> int:
    staging = _parse_env_file(ENV_DIR / "staging.env")
    production = _parse_env_file(ENV_DIR / "production.env")
    staging_keys = sorted(staging.keys())
    prod_keys = sorted(production.keys())
    if staging_keys != prod_keys:
        staging_only = sorted(set(staging_keys) - set(prod_keys))
        prod_only = sorted(set(prod_keys) - set(staging_keys))
        raise RuntimeError(
            "staging/prod não estão espelhados.\n"
            f"Somente staging: {staging_only}\n"
            f"Somente production: {prod_only}"
        )
    print(f"Ambientes espelhados: {len(staging_keys)} chave(s) em comum.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deploy control plane (blue/green + canary).")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-env-mirror")
    validate.set_defaults(command_fn=lambda _args: command_validate_env_mirror())

    release = sub.add_parser("release")
    release.add_argument("--env", required=True, choices=["staging", "production"])
    release.add_argument("--version", required=True)
    release.add_argument("--strategy", required=True, choices=["blue-green", "canary"])
    release.add_argument("--canary-weight", type=int, default=10)
    release.add_argument("--promote", action="store_true")
    release.add_argument("--dry-run", action="store_true")
    release.set_defaults(
        command_fn=lambda args: command_release(
            ReleaseArgs(
                environment=args.env,
                version=args.version,
                strategy=args.strategy,
                canary_weight=args.canary_weight,
                promote=bool(args.promote),
                dry_run=bool(args.dry_run),
            )
        )
    )

    rollback = sub.add_parser("rollback")
    rollback.add_argument("--env", required=True, choices=["staging", "production"])
    rollback.add_argument("--strategy", default="auto", choices=["auto", "blue-green", "canary"])
    rollback.add_argument("--to-version", required=False)
    rollback.add_argument("--dry-run", action="store_true")
    rollback.set_defaults(
        command_fn=lambda args: command_rollback(
            environment=args.env,
            strategy=args.strategy,
            to_version=args.to_version,
            dry_run=bool(args.dry_run),
        )
    )

    state = sub.add_parser("print-state")
    state.add_argument("--env", required=True, choices=["staging", "production"])
    state.set_defaults(
        command_fn=lambda args: (
            print(json.dumps(_load_state(args.env), ensure_ascii=False, indent=2)),
            0,
        )[1]
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return int(args.command_fn(args))
    except Exception as exc:
        print(f"deployctl error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
