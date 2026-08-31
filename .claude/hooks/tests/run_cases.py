#!/usr/bin/env python3
"""Оффлайн-прогон таблицы команд для block_wide_fs_search.py.

Не требует живой сессии Claude Code: собирает тот же JSON, что хук получает
на stdin от PreToolUse, запускает хук-скрипт как реальный подпроцесс и
сверяет код возврата (0 = allow, 2 = block) с ожиданием из cases.tsv.

    python .claude/hooks/tests/run_cases.py
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
HOOK = HERE.parent / "block_wide_fs_search.py"
CASES = HERE / "cases.tsv"

CWD_VALUES = {
    "PROJ": "/c/Users/dev/Workspace/example-project",
    "ROOT": "/",
    "HOME": "/c/Users/dev",
}
CWD_VALUES["SUBDIR"] = CWD_VALUES["PROJ"] + "/src"


def load_cases() -> list[tuple[str, str, str, str]]:
    rows = []
    for line in CASES.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        expect, tool_name, cwd_key, command = line.split("\t", 3)
        rows.append((expect, tool_name, CWD_VALUES[cwd_key], command))
    return rows


def run_case(tool_name: str, cwd: str, command: str) -> tuple[int, str]:
    payload = json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {"command": command},
            "cwd": cwd,
        }
    )
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        # Кодировка задаётся явно как UTF-8, а не через `text=True`
        # (который читал бы дочерний вывод в локальной кодировке хоста —
        # на Windows это часто cp1251/cp866, а не UTF-8, который сам хук
        # пишет после reconfigure). `errors="replace"` — чтобы регрессия
        # кодировки в хуке превратилась в видимый мусор в stderr и провал
        # BLOCK_MARKER-проверки ниже, а не в необработанное исключение,
        # роняющее весь прогон таблицы.
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    return proc.returncode, proc.stderr.strip()


# Подстрока из сообщения хука (block_wide_fs_search.py, main()) — если её
# нет в stderr BLOCK-кейса при декодировании как UTF-8, читающий получит
# мусор вместо причины блокировки.
BLOCK_MARKER = "Заблокировано хуком"


def main() -> int:
    # Windows-консоль по умолчанию не UTF-8 — без этого русский текст в
    # выводе (в т.ч. итоговая строка) превращается в мусор.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    rows = load_cases()
    failures = []
    for expect, tool_name, cwd, command in rows:
        code, stderr = run_case(tool_name, cwd, command)
        got = "BLOCK" if code == 2 else "ALLOW" if code == 0 else f"ERROR({code})"
        ok = got == expect
        if ok and expect == "BLOCK" and BLOCK_MARKER not in stderr:
            ok = False
            got = "BLOCK(мусор в stderr)"
        status = "ok" if ok else "FAIL"
        if status == "FAIL":
            failures.append((expect, got, tool_name, command, stderr))
        print(f"  {status:4} expect={expect:5} got={got:5} [{tool_name}] {command}")

    print()
    print(f"Итого: {len(rows)} кейсов, {len(failures)} провалено.")
    if failures:
        print()
        print("Провалы:")
        for expect, got, tool_name, command, stderr in failures:
            print(f"  expect={expect} got={got} [{tool_name}] {command}")
            if stderr:
                print(f"    stderr: {stderr}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
