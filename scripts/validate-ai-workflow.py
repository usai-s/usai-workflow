#!/usr/bin/env python3
"""Проверяет согласованность установленных AI-workflow адаптеров.

Это не validator state machine фич. Скрипт проверяет только статическую
конфигурацию: общий feature-контракт, thin adapters, hook source of truth и
model-tier parity между vendor-профилями и таблицей ролей в routing.md.

Адаптеры опциональны: проверяются только установленные (`.claude/`,
`.codex/`). Если не установлен ни один — скрипт сообщает об этом и выходит
успешно: валидировать нечего.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANONICAL = "docs/ai-workflow/feature.md"

ROLE_STAGES = {
    "legacy-analyst": "00-legacy-analysis.md",
    "business-analyst": "01-business-analysis.md",
    "requirements-reviewer": "02-requirements-review.md",
    "ux-designer": "03-ux-design.md",
    "backend-developer": "04-backend.md",
    "frontend-developer": "05-frontend.md",
    "qa-engineer": "04-backend.md",
    "code-reviewer": "06-review-complete.md",
}

TIER_MODELS = {
    "deep": ("opus", "gpt-5.6", "high"),
    "standard": ("sonnet", "gpt-5.6-terra", "medium"),
    "fast": ("haiku", "gpt-5.6-luna", "low"),
}


def read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise FileNotFoundError(relative)
    return path.read_text(encoding="utf-8")


def frontmatter(relative: str) -> dict[str, str]:
    text = read(relative)
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"{relative}: отсутствует YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError(f"{relative}: frontmatter не закрыт") from error

    result: dict[str, str] = {}
    for line in lines[1:end]:
        match = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*)$", line)
        if match:
            result[match.group(1)] = match.group(2).strip()
    return result


def role_tiers() -> dict[str, str]:
    """Читает canonical role→tier table непосредственно из routing.md."""
    result: dict[str, str] = {}
    pattern = re.compile(r"^\|\s*([a-z]+(?:-[a-z]+)*)\s*\|\s*`(deep|standard|fast)`\s*\|")
    for line in read("docs/ai-workflow/routing.md").splitlines():
        match = pattern.match(line)
        if match and match.group(1) in ROLE_STAGES:
            result[match.group(1)] = match.group(2)
    missing = sorted(set(ROLE_STAGES) - set(result))
    if missing:
        raise ValueError(f"routing.md: нет role→tier для {', '.join(missing)}")
    return result


def check_claude(errors: list[str], tiers: dict[str, str]) -> None:
    adapter_path = ".claude/commands/feature.md"
    try:
        adapter = read(adapter_path)
    except FileNotFoundError:
        errors.append(f"не найден {adapter_path}")
        return

    if CANONICAL not in adapter:
        errors.append(f"{adapter_path}: не подключён общий контракт {CANONICAL}")
    if len(adapter) > 3_000:
        errors.append(f"{adapter_path}: адаптер разросся и дублирует общий контракт")
    if "$ARGUMENTS" not in adapter:
        errors.append(f"{adapter_path}: потеряна передача $ARGUMENTS")
    if (ROOT / ".claude/skills/feature").exists():
        errors.append(".claude/skills/feature запрещён: он перехватит рабочий /feature command")

    try:
        meta = frontmatter(adapter_path)
        if not meta.get("description"):
            errors.append(f"{adapter_path}: отсутствует description")
    except ValueError as error:
        errors.append(str(error))

    try:
        json.loads(read(".claude/settings.json"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        errors.append(f".claude/settings.json: невалидный JSON: {error}")

    for role in ROLE_STAGES:
        tier = tiers.get(role)
        if tier not in TIER_MODELS:
            continue
        claude_model = TIER_MODELS[tier][0]
        claude_path = f".claude/agents/{role}.md"
        try:
            meta = frontmatter(claude_path)
            if meta.get("model") != claude_model:
                errors.append(f"{claude_path}: tier {tier} ожидает model: {claude_model}")
        except (FileNotFoundError, ValueError) as error:
            errors.append(str(error))


def check_codex(errors: list[str], tiers: dict[str, str]) -> None:
    required = [
        ".agents/skills/feature/SKILL.md",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".codex/hooks/run-pre-tool-use.ps1",
    ]
    missing = [rel for rel in required if not (ROOT / rel).is_file()]
    if missing:
        errors.extend(f"не найден {rel}" for rel in missing)
        return

    skill = read(".agents/skills/feature/SKILL.md")
    if CANONICAL not in skill:
        errors.append(f".agents/skills/feature/SKILL.md: не подключён общий контракт {CANONICAL}")
    if len(skill) > 3_000:
        errors.append(".agents/skills/feature/SKILL.md: адаптер разросся и дублирует общий контракт")
    try:
        meta = frontmatter(".agents/skills/feature/SKILL.md")
        if meta.get("name") != "feature":
            errors.append("Codex skill должен называться feature")
        if not meta.get("description"):
            errors.append("Codex skill: отсутствует description")
    except ValueError as error:
        errors.append(str(error))

    try:
        config = tomllib.loads(read(".codex/config.toml"))
        concurrency = config.get("agents", {}).get("max_concurrent_threads_per_session")
        if not isinstance(concurrency, int) or concurrency < 1:
            errors.append(".codex/config.toml: max_concurrent_threads_per_session должен быть > 0")
    except tomllib.TOMLDecodeError as error:
        errors.append(f".codex/config.toml: невалидный TOML: {error}")

    for role, stage_file in ROLE_STAGES.items():
        tier = tiers.get(role)
        if tier not in TIER_MODELS:
            continue
        _, codex_model, effort = TIER_MODELS[tier]
        codex_path = f".codex/agents/{role}.toml"
        try:
            codex = tomllib.loads(read(codex_path))
            if codex.get("name") != role:
                errors.append(f"{codex_path}: name должен совпадать с {role}")
            for field in ("description", "developer_instructions"):
                if not codex.get(field):
                    errors.append(f"{codex_path}: отсутствует {field}")
            if codex.get("model") != codex_model:
                errors.append(f"{codex_path}: tier {tier} ожидает model {codex_model}")
            if codex.get("model_reasoning_effort") != effort:
                errors.append(f"{codex_path}: tier {tier} ожидает effort {effort}")
            if role == "code-reviewer" and codex.get("sandbox_mode") != "read-only":
                errors.append(f"{codex_path}: code-reviewer должен быть read-only")
            if stage_file not in codex.get("developer_instructions", ""):
                errors.append(f"{codex_path}: нет ссылки на {stage_file}")
        except (FileNotFoundError, tomllib.TOMLDecodeError) as error:
            errors.append(f"{codex_path}: невалидный TOML: {error}")

    try:
        hooks = json.loads(read(".codex/hooks.json"))
        handler = hooks["hooks"]["PreToolUse"][0]["hooks"][0]
        if hooks["hooks"]["PreToolUse"][0].get("matcher") != "^Bash$":
            errors.append(".codex/hooks.json: PreToolUse matcher должен быть ^Bash$")
        if ".claude/hooks/block_wide_fs_search.py" not in handler.get("command", ""):
            errors.append(".codex/hooks.json: POSIX hook не использует общую Claude policy")
        if ".codex/hooks/run-pre-tool-use.ps1" not in handler.get("commandWindows", ""):
            errors.append(".codex/hooks.json: отсутствует Windows adapter")
        windows_adapter = read(".codex/hooks/run-pre-tool-use.ps1")
        if ".claude\\hooks\\block_wide_fs_search.py" not in windows_adapter:
            errors.append("Codex Windows hook не использует общую Claude policy")
        if "toolName.Value = 'PowerShell'" not in windows_adapter:
            errors.append("Codex Windows hook не нормализует Bash tool name в PowerShell")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        errors.append(f".codex/hooks.json: неожиданная структура: {error}")

    # Codex опирается на общую policy из adapter-claude.
    if not (ROOT / ".claude/hooks/block_wide_fs_search.py").is_file():
        errors.append("adapter-codex требует .claude/hooks/block_wide_fs_search.py (модуль adapter-claude)")


def main() -> int:
    errors: list[str] = []

    if not (ROOT / CANONICAL).is_file():
        errors.append(f"не найден {CANONICAL}")
        return report(errors, [])

    canonical = read(CANONICAL)
    for marker in (
        "docs/ai-workflow/README.md",
        "docs/ai-workflow/routing.md",
        "scripts/new-task.ps1",
        "gate-3",
        "code-reviewer",
    ):
        if marker not in canonical:
            errors.append(f"{CANONICAL}: нет обязательной ссылки {marker}")

    try:
        tiers = role_tiers()
    except (FileNotFoundError, ValueError) as error:
        errors.append(str(error))
        tiers = {}

    checked: list[str] = []
    if (ROOT / ".claude").is_dir():
        checked.append("claude")
        check_claude(errors, tiers)
    if (ROOT / ".codex").is_dir():
        checked.append("codex")
        check_codex(errors, tiers)

    return report(errors, checked)


def report(errors: list[str], checked: list[str]) -> int:
    if errors:
        print("AI workflow adapters: ПРОВАЛ", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    if checked:
        print(f"AI workflow adapters: OK ({', '.join(checked)})")
    else:
        print("AI workflow adapters: адаптеры не установлены, проверять нечего")
    return 0


if __name__ == "__main__":
    sys.exit(main())
