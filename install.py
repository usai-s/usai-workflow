#!/usr/bin/env python3
"""usai-workflow installer — ставит AI workflow в целевой проект.

Движок ничего не знает о конкретных модулях: каждый модуль описан манифестом
`module.toml` и каталогом `files/`, зеркалящим целевую раскладку. Добавить
модуль = добавить каталог в `modules/`; код движка не меняется.

Использование:
    python install.py --target <путь-к-проекту>              # диалог
    python install.py --target <путь> --all --yes            # всё, без вопросов
    python install.py --target <путь> --modules adapter-claude --yes
    python install.py --list                                 # список модулей
    python install.py --target <путь> --dry-run --all        # показать план

Поведение при конфликте: существующий файл с другим содержимым останавливает
установку ДО первой записи (двухфазный план). `--force` перезаписывает.
Файлы из списка `seed` манифеста — проектные заготовки (AGENTS.md, конфиг
verify и т.п.): создаются только если их ещё нет, существующие не трогаются
и конфликтом не считаются.

После установки в целевом проекте появляется `.usai-workflow.lock` — версия,
список модулей и sha256 каждого поставленного файла (задел для `update`).

Требования: Python >= 3.11 (tomllib), только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCK_NAME = ".usai-workflow.lock"


@dataclass
class Module:
    id: str
    title: str
    description: str
    root: Path                      # каталог модуля (содержит module.toml и files/)
    requires: list[str] = field(default_factory=list)
    seed: list[str] = field(default_factory=list)   # целевые пути-заготовки
    always: bool = False            # ставится всегда, без вопроса
    question: str = ""

    @property
    def files_dir(self) -> Path:
        return self.root / "files"


@dataclass
class PlannedFile:
    src: Path
    rel: str                        # путь относительно целевого проекта, POSIX
    module: str
    is_seed: bool


def load_module(root: Path) -> Module:
    manifest = root / "module.toml"
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    for key in ("id", "title", "description"):
        if not data.get(key):
            raise SystemExit(f"{manifest}: отсутствует обязательное поле {key!r}")
    if not (root / "files").is_dir():
        raise SystemExit(f"{root}: нет каталога files/")
    return Module(
        id=data["id"],
        title=data["title"],
        description=data["description"],
        root=root,
        requires=list(data.get("requires", [])),
        seed=list(data.get("seed", [])),
        always=bool(data.get("always", False)),
        question=data.get("question", ""),
    )


def discover() -> dict[str, Module]:
    modules: dict[str, Module] = {}
    for root in [HERE / "core", *sorted((HERE / "modules").iterdir())]:
        if not (root / "module.toml").is_file():
            continue
        m = load_module(root)
        if m.id in modules:
            raise SystemExit(f"дубль id модуля: {m.id}")
        modules[m.id] = m
    if "core" not in modules:
        raise SystemExit("не найден core/module.toml — репозиторий повреждён?")
    return modules


def resolve_selection(modules: dict[str, Module], wanted: list[str]) -> list[Module]:
    """Замыкание по requires, порядок: core, затем по мере обхода."""
    seen: list[str] = []

    def add(mid: str) -> None:
        if mid in seen:
            return
        if mid not in modules:
            raise SystemExit(
                f"неизвестный модуль {mid!r}; доступны: {', '.join(sorted(modules))}"
            )
        for dep in modules[mid].requires:
            add(dep)
        seen.append(mid)

    add("core")
    for mid in wanted:
        add(mid)
    return [modules[mid] for mid in seen]


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        answer = input(prompt + suffix).strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes", "д", "да"):
            return True
        if answer in ("n", "no", "н", "нет"):
            return False
        print("  ответьте y или n")


def interactive_selection(modules: dict[str, Module]) -> list[str]:
    wanted: list[str] = []
    optional = [m for m in modules.values() if not m.always]
    if not optional:
        return wanted
    print("Выберите модули (ядро ставится всегда):\n")
    for m in optional:
        question = m.question or f"Установить модуль «{m.title}»?"
        note = f" (требует: {', '.join(m.requires)})" if m.requires else ""
        print(f"  {m.id} — {m.description}")
        if ask_yes_no(f"  {question}{note}", default=True):
            wanted.append(m.id)
        print()
    return wanted


def plan_files(selection: list[Module]) -> list[PlannedFile]:
    planned: list[PlannedFile] = []
    owners: dict[str, str] = {}
    for m in selection:
        seeds = set(m.seed)
        for src in sorted(m.files_dir.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(m.files_dir).as_posix()
            if rel in owners:
                raise SystemExit(
                    f"файл {rel} есть и в {owners[rel]}, и в {m.id} — "
                    "модули не должны пересекаться по файлам"
                )
            owners[rel] = m.id
            planned.append(PlannedFile(src=src, rel=rel, module=m.id, is_seed=rel in seeds))
    return planned


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(target: Path, selection: list[Module], planned: list[PlannedFile],
            force: bool, dry_run: bool) -> int:
    conflicts: list[str] = []
    to_copy: list[PlannedFile] = []
    skipped_seeds: list[str] = []
    identical: list[str] = []

    for pf in planned:
        dst = target / pf.rel
        if dst.exists():
            if pf.is_seed:
                skipped_seeds.append(pf.rel)
                continue
            if sha256(dst) == sha256(pf.src):
                identical.append(pf.rel)
                continue
            if not force:
                conflicts.append(pf.rel)
                continue
        to_copy.append(pf)

    if conflicts:
        print("Установка остановлена: конфликты (файл существует и отличается):",
              file=sys.stderr)
        for rel in conflicts:
            print(f"  {rel}", file=sys.stderr)
        print("Ничего не записано. Разберитесь с файлами или используйте --force.",
              file=sys.stderr)
        return 1

    verb = "будет записан" if dry_run else "записан"
    for pf in to_copy:
        dst = target / pf.rel
        print(f"  {verb}: {pf.rel}  [{pf.module}]")
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pf.src, dst)
    for rel in skipped_seeds:
        print(f"  оставлен как есть (seed): {rel}")
    if identical:
        print(f"  без изменений: {len(identical)} файл(ов)")

    if not dry_run:
        version = (HERE / "VERSION").read_text(encoding="utf-8").strip()
        lock = {
            "version": version,
            "modules": [m.id for m in selection],
            "files": {
                pf.rel: {"sha256": sha256(pf.src), "module": pf.module}
                for pf in planned if not pf.is_seed
            },
            "seeds": sorted(pf.rel for pf in planned if pf.is_seed),
        }
        (target / LOCK_NAME).write_text(
            json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nГотово: {len(to_copy)} файл(ов), lock — {LOCK_NAME}.")
        print("Дальше: заполните AGENTS.md (слоты проекта) и scripts/verify.config.sh.")
    else:
        print(f"\n(dry-run) файлов к записи: {len(to_copy)}")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    parser = argparse.ArgumentParser(description="Установка usai-workflow в проект.")
    parser.add_argument("--target", help="каталог целевого проекта")
    parser.add_argument("--modules", help="модули через запятую (ядро — всегда)")
    parser.add_argument("--all", action="store_true", help="все модули без вопросов")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="не задавать вопросов (для --modules/--all)")
    parser.add_argument("--force", action="store_true",
                        help="перезаписывать отличающиеся файлы")
    parser.add_argument("--dry-run", action="store_true", help="только показать план")
    parser.add_argument("--list", action="store_true", help="показать модули и выйти")
    args = parser.parse_args()

    modules = discover()

    if args.list:
        for m in modules.values():
            mark = "всегда" if m.always else "опция"
            deps = f", требует: {', '.join(m.requires)}" if m.requires else ""
            print(f"  {m.id:<16} [{mark}{deps}] {m.description}")
        return 0

    if not args.target:
        parser.error("нужен --target (или --list)")
    target = Path(args.target).resolve()
    if not target.is_dir():
        parser.error(f"целевой каталог не существует: {target}")

    if args.all:
        wanted = [m.id for m in modules.values()]
    elif args.modules:
        wanted = [x.strip() for x in args.modules.split(",") if x.strip()]
    elif args.yes:
        parser.error("--yes без --all/--modules: непонятно, что ставить")
    else:
        wanted = interactive_selection(modules)

    selection = resolve_selection(modules, wanted)
    print(f"\nУстановка в {target}: {', '.join(m.id for m in selection)}\n")
    planned = plan_files(selection)
    return install(target, selection, planned, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
