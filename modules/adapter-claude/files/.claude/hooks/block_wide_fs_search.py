#!/usr/bin/env python3
"""PreToolUse hook: блокирует поиск/листинг всего диска или всего профиля.

Читает JSON события PreToolUse из stdin (поле tool_input.command — сырая
командная строка, как её видит шелл), решает, блокировать ли вызов, и
сообщает решение кодом возврата — это единственный канал, который остаётся
стабильным во времени и не зависит от точного имени полей во вложенном JSON:

    exit 0  — разрешить, ничего не печатать (тихо).
    exit 2  — заблокировать; stderr уходит агенту как причина и подсказка,
              куда идти вместо этого.

Отказоустойчивость — намеренно fail-open: любая ошибка разбора входа
(невалидный JSON, `tool_input`/`cwd` неожиданного типа, внутреннее
исключение) приводит к `exit 0`, а не к падению с трейсбеком. Ложный ALLOW
при сбое разбора безопаснее, чем зависшая или заблокированная по внутренней
ошибке хука легитимная команда, которую агент не может продиагностировать.
См. `try/except` в `main()`.

Причина, почему это отдельный скрипт, а не только `permissions.deny`:
deny сопоставляет ПРЕФИКС команды с фиксированным списком строк-паттернов
(бьётся составными командами, кавычками, разным порядком флагов).
Здесь — реальный (упрощённый) разбор командной строки: составные команды
разбиваются на подкоманды по `&&`, `||`, `;`, `|`, `|&`, `&`, переносам
строк; отслеживается смена рабочего каталога через `cd`; пути разрешаются
относительно него. Это не полноценный шелл-парсер (он и не должен им быть — граница защиты
описана в README.md рядом), но он закрывает конкретные, наблюдавшиеся на
практике дыры.

Оффлайн-таблица команд для проверки — .claude/hooks/tests/cases.tsv,
прогоняется .claude/hooks/tests/run_cases.py без живой сессии.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import shlex
import sys

# --- Разбор командной строки на подкоманды -----------------------------------

_OP2 = ("&&", "||", "|&")
_OP1 = (";", "|", "&", "\n")


def split_subcommands(command: str, powershell: bool) -> list[str]:
    """Режет составную команду по неэкранированным `&&`, `||`, `;`, `|`, `&`.

    Учитывает одинарные/двойные кавычки: разделитель внутри кавычек не
    считается разделителем. В Bash обратный слэш экранирует следующий
    символ (в т.ч. разделитель); в PowerShell обратный слэш — обычный
    символ пути (`C:\\`), экранирования не делает.
    """
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if not powershell and ch == "\\" and i + 1 < n:
            buf.append(ch)
            buf.append(command[i + 1])
            i += 2
            continue
        two = command[i : i + 2]
        if two in _OP2:
            parts.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch in _OP1:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p for p in (p.strip() for p in parts) if p]


def tokenize(subcommand: str, powershell: bool) -> list[str]:
    if powershell:
        # Bash-семантика shlex здесь неверна: `\` в Windows-путях — не
        # escape-символ, а `C:\` с ничем после (конец токена) валит
        # posix-режим shlex исключением "No escaped character".
        tokens: list[str] = []
        buf: list[str] = []
        quote: str | None = None
        for ch in subcommand:
            if quote:
                if ch == quote:
                    quote = None
                else:
                    buf.append(ch)
                continue
            if ch in ("'", '"'):
                quote = ch
                continue
            if ch.isspace():
                if buf:
                    tokens.append("".join(buf))
                    buf = []
                continue
            buf.append(ch)
        if buf:
            tokens.append("".join(buf))
        return tokens
    try:
        return shlex.split(subcommand, posix=True)
    except ValueError:
        # Несбалансированные кавычки и т.п. — не роняем хук, работаем с тем,
        # что есть, наивным разбиением. Ошибка на стороне самой команды
        # проявится и без нас, когда её реально выполнит шелл.
        return subcommand.split()


_WRAPPERS = {"sudo", "time", "nice", "nohup", "env", "xargs"}
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Флаги обёрток, которые забирают ОТДЕЛЬНЫЙ следующий токен как свой аргумент
# (в отличие от `-n`/`-i` и т.п., которые самодостаточны, или `-I{}`, где
# аргумент уже приклеен к флагу в том же токене). Список практический, не
# исчерпывающий полный man — достаточно, чтобы не потерять начало реальной
# команды при её поиске после обёртки.
_WRAPPER_ARG_FLAGS: dict[str, set[str]] = {
    "sudo": {"-u", "-g", "-p", "-h", "-C", "-D", "-U", "-r", "-T", "-a"},
    "env": {"-u", "-C", "-S"},
    "nice": {"-n"},
    "xargs": {"-I", "-i", "-L", "-n", "-P", "-s", "-d", "-a", "-E", "-l", "-x"},
}


def strip_wrappers(words: list[str]) -> list[str]:
    """Снимает `VAR=val`, `sudo`, `time`, `nice`, `nohup`, `env`, `xargs`,
    `timeout N` — вместе с их собственными флагами (в т.ч. `sudo -n`,
    `sudo -u root`, `nice -n 10`, `env -i`, `xargs -I{}`), а не только с
    голым именем обёртки."""
    i = 0
    while i < len(words):
        w = words[i]
        if _ASSIGN_RE.match(w):
            i += 1
            continue
        if w == "timeout":
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 1
            if i < len(words):
                i += 1  # длительность
            continue
        if w in _WRAPPERS:
            arg_flags = _WRAPPER_ARG_FLAGS.get(w, frozenset())
            i += 1
            while i < len(words) and words[i].startswith("-"):
                flag = words[i]
                i += 1
                if flag == "--":
                    break
                if flag in arg_flags and i < len(words):
                    i += 1  # отдельный аргумент флага, не начало команды
            continue
        break
    return words[i:]


# --- Разрешение путей и проверка «слишком широко» -----------------------------

_HOME_CANDIDATES = [
    os.environ.get("HOME", ""),
    os.environ.get("USERPROFILE", "").replace("\\", "/"),
]
_HOME_CANDIDATES = [h for h in _HOME_CANDIDATES if h]

# `$HOME`/`${HOME}`/`$USERPROFILE`/`${USERPROFILE}`/`$env:USERPROFILE`/
# `%USERPROFILE%` — переменные окружения, которыми реально искали пакеты
# NuGet в инциденте (`find $HOME/.nuget/...`, `Get-ChildItem
# $env:USERPROFILE -Recurse`). Хук не исполняет шелл и не знает истинного
# значения переменной в сессии агента — подставляет своё представление о
# домашнем каталоге (то же, что уже используется для `~`); текстовое
# совпадение, а не настоящее раскрытие переменных.
_HOME_VAR_RES = [
    re.compile(r"^\$\{HOME\}"),
    re.compile(r"^\$HOME(?![A-Za-z0-9_])"),
    re.compile(r"^\$\{USERPROFILE\}"),
    re.compile(r"^\$USERPROFILE(?![A-Za-z0-9_])"),
    re.compile(r"^\$env:USERPROFILE(?![A-Za-z0-9_])", re.I),
    re.compile(r"^%USERPROFILE%", re.I),
]


def _expand_home_vars(p: str) -> str:
    if not _HOME_CANDIDATES:
        return p
    home = _HOME_CANDIDATES[0]
    for pat in _HOME_VAR_RES:
        m = pat.match(p)
        if m:
            return home + p[m.end():]
    return p


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    p = posixpath.normpath(p)
    if p != "/" and p.endswith("/"):
        p = p[:-1]
    return p


def resolve(raw: str, cwd: str) -> str:
    """Разрешает `raw` в абсолютный путь относительно `cwd` (симулированного)."""
    p = _expand_home_vars(raw)
    if p == "~":
        p = _HOME_CANDIDATES[0] if _HOME_CANDIDATES else "~"
    elif p.startswith("~/"):
        p = (_HOME_CANDIDATES[0] if _HOME_CANDIDATES else "~") + p[1:]
    p = p.replace("\\", "/")
    is_abs = bool(re.match(r"^([A-Za-z]:)?/", p))
    if not is_abs:
        p = cwd.rstrip("/") + "/" + p
    return _norm(p)


# Форма диска в Git Bash (`/c`, `/d`, ...) обобщена на любую букву диска
# симметрично Windows-нативной форме (`C:`, `D:`, ...) — раньше здесь был
# захардкожен только `/c`, из-за чего `find /d` (POSIX-форма другого диска)
# проходил, а `Get-ChildItem D:\ -Recurse` (нативная форма того же диска)
# уже блокировался: асимметрия без причины, диск D: не безопаснее диска C:.
_ROOT_LIKE_RES = [
    re.compile(r"^/$"),
    re.compile(r"^/[a-z]$", re.I),
    re.compile(r"^[a-z]:$", re.I),
    re.compile(r"^/[a-z]/users$", re.I),
    re.compile(r"^[a-z]:/users$", re.I),
    re.compile(r"^/[a-z]/users/[^/]+$", re.I),
    re.compile(r"^[a-z]:/users/[^/]+$", re.I),
]


def is_root_like(resolved_path: str) -> bool:
    return any(r.match(resolved_path) for r in _ROOT_LIKE_RES)


# --- Правила по конкретным командам --------------------------------------------

_FIND_PRE_PATH_OPTS = {"-H", "-L", "-P", "-O0", "-O1", "-O2", "-O3"}


def find_maxdepth(args: list[str]) -> int | None:
    """Значение `-maxdepth N`/`-maxdepth=N`, если оно есть и разбирается."""
    for i, a in enumerate(args):
        if a == "-maxdepth" and i + 1 < len(args):
            try:
                return int(args[i + 1])
            except ValueError:
                return None
        if a.startswith("-maxdepth="):
            try:
                return int(a.split("=", 1)[1])
            except ValueError:
                return None
    return None


def find_paths(args: list[str]) -> list[str]:
    idx = 0
    while idx < len(args) and args[idx] in _FIND_PRE_PATH_OPTS:
        idx += 1
    if idx < len(args) and args[idx] == "-D":
        idx += 2
    paths: list[str] = []
    while idx < len(args) and not args[idx].startswith("-") and args[idx] not in ("(", "!", ")"):
        paths.append(args[idx])
        idx += 1
    return paths


_RECURSIVE_SHORT_RE = re.compile(r"^-[A-Za-z]*[rR][A-Za-z]*$")


def grep_is_recursive(args: list[str]) -> bool:
    for a in args:
        if a in ("-r", "-R", "--recursive"):
            return True
        if a.startswith("--recursive"):
            return True
        if a.startswith("-") and not a.startswith("--") and _RECURSIVE_SHORT_RE.match(a):
            return True
    return False


def grep_paths(args: list[str]) -> list[str]:
    non_flags: list[str] = []
    has_e_flag = False
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in ("-e", "--regexp", "-f", "--file"):
            has_e_flag = True
            skip_next = True
            continue
        if a.startswith("-"):
            continue
        non_flags.append(a)
    if has_e_flag:
        return non_flags
    return non_flags[1:]  # первый нефлаговый токен — паттерн, не путь


def ls_is_recursive(args: list[str]) -> bool:
    for a in args:
        if a in ("-R", "--recursive"):
            return True
        if a.startswith("--recursive"):
            return True
        if re.match(r"^-Rec", a, re.I):
            return True
        if a.startswith("-") and not a.startswith("--") and "R" in a[1:]:
            return True
    return False


def non_flag_args(args: list[str], extra_flag_re: re.Pattern | None = None) -> list[str]:
    out = []
    for a in args:
        if a.startswith("-"):
            continue
        if extra_flag_re and extra_flag_re.match(a):
            continue
        out.append(a)
    return out


_DIR_CMD_FLAG_RE = re.compile(r"^/[A-Za-z]$")


def gci_is_recursive(args: list[str], base: str) -> bool:
    for a in args:
        if re.match(r"^-Rec", a, re.I):
            return True
        if base == "dir" and re.match(r"^/S$", a, re.I):
            return True
    return False


def gci_paths(args: list[str], base: str) -> list[str]:
    paths: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        low = a.lower()
        if low in ("-path", "-literalpath"):
            if i + 1 < len(args):
                paths.append(args[i + 1])
                i += 2
                continue
        if low.startswith("-path=") or low.startswith("-literalpath="):
            paths.append(a.split("=", 1)[1])
            i += 1
            continue
        if a.startswith("-") or (base == "dir" and _DIR_CMD_FLAG_RE.match(a)):
            i += 1
            continue
        paths.append(a)
        i += 1
    return paths


# --- Главная проверка одной подкоманды -----------------------------------------


def check_subcommand(words: list[str], cwd: str) -> tuple[bool, str] | None:
    """Возвращает (заблокировать?, читаемое описание) либо None, если правило
    к этой команде не относится."""
    if not words:
        return None
    base = os.path.basename(words[0])
    base = re.sub(r"\.exe$", "", base, flags=re.I)
    base_l = base.lower()
    args = words[1:]

    if base_l in ("bash", "sh", "zsh") and "-c" in args:
        # `bash -c '...'` / `sh -c '...'` — настоящая команда не первый
        # токен, а строка-аргумент `-c`; кавычки уже сняты токенайзером
        # (весь текст пришёл одним словом), прогоняем её тем же evaluate.
        idx = args.index("-c")
        if idx + 1 < len(args):
            blocked, reason = evaluate(args[idx + 1], cwd, powershell=False)
            if blocked:
                return True, f"{base_l} -c: {reason}"
        return False, ""

    if base_l == "find":
        maxdepth = find_maxdepth(args)
        if maxdepth is not None and maxdepth <= 1:
            # `-maxdepth 0`/`-maxdepth 1` не спускается вглубь — дёшево и
            # безопасно независимо от пути (не может съесть часы CPU, ради
            # чего вообще существует это правило). Именно этой формой сам
            # разработчик проверял факты про `/` и `/proc/registry` в
            # круге 2 — раньше она же и блокировалась, что было ложным
            # срабатыванием на собственной безопасной разведке.
            return False, ""
        paths = find_paths(args) or [cwd]
        for raw in paths:
            resolved = resolve(raw, cwd)
            if is_root_like(resolved):
                return True, f"find по «{raw}» (= {resolved})"
        return False, ""

    if base_l in ("rg", "ripgrep"):
        if "--files" in args:
            candidates = non_flag_args(args) or [cwd]
        else:
            nf = non_flag_args(args)
            candidates = nf[1:] if len(nf) > 1 else ([cwd] if not nf else [])
        for raw in candidates:
            resolved = resolve(raw, cwd)
            if is_root_like(resolved):
                return True, f"rg по «{raw}» (= {resolved})"
        return False, ""

    if base_l in ("grep", "egrep", "fgrep"):
        if not grep_is_recursive(args):
            return False, ""
        candidates = grep_paths(args) or [cwd]
        for raw in candidates:
            resolved = resolve(raw, cwd)
            if is_root_like(resolved):
                return True, f"grep -r по «{raw}» (= {resolved})"
        return False, ""

    if base_l in ("ls", "gci", "dir", "get-childitem"):
        recursive = ls_is_recursive(args) if base_l == "ls" else gci_is_recursive(args, base_l)
        if not recursive:
            return False, ""
        if base_l == "ls":
            candidates = non_flag_args(args) or [cwd]
        else:
            candidates = gci_paths(args, base_l) or [cwd]
        for raw in candidates:
            resolved = resolve(raw, cwd)
            if is_root_like(resolved):
                return True, f"{words[0]} -Recurse/-R по «{raw}» (= {resolved})"
        return False, ""

    if base_l == "du":
        candidates = non_flag_args(args) or [cwd]
        for raw in candidates:
            resolved = resolve(raw, cwd)
            if is_root_like(resolved):
                return True, f"du по «{raw}» (= {resolved})"
        return False, ""

    if base_l == "tree":
        candidates = non_flag_args(args) or [cwd]
        for raw in candidates:
            resolved = resolve(raw, cwd)
            if is_root_like(resolved):
                return True, f"tree по «{raw}» (= {resolved})"
        return False, ""

    return None


SUGGESTION = (
    "Поиск по всему диску или всему профилю пользователя запрещён — он "
    "перемалывает node_modules, кэши пакетов, слои Docker и держит CPU часами "
    "(см. AGENTS.md, пункт «Не искать по всему диску» в разделе «Жёсткие "
    "правила»). Вместо этого:\n"
    "  - файлы репозитория — инструменты Glob/Grep, а не find/grep -r/ls -R;\n"
    "  - кэш пакетов — иди сразу в его подкаталог "
    "(~/.nuget/packages/<пакет>/, ~/.npm/..., а не в кэш целиком);\n"
    "  - путь неизвестен — сузь до конкретного поддерева "
    "(find src -name '*.ext'), а не начинай с /, /c, C:\\ или домашнего "
    "каталога целиком."
)


_LEADING_KEYWORDS = {"do", "then", "else", "!"}


def _strip_group_chars(sub: str) -> str:
    """Снимает один приклеенный без пробела `(`/`)` группировки-подшелла,
    например `(find / -name x)`. Не полноценный баланс скобок — эвристика
    для конкретной, самой частой формы; вложенные/несбалансированные случаи
    вне гарантии (см. докстринг модуля про границу защиты)."""
    if sub.startswith("("):
        sub = sub[1:]
    if sub.endswith(")"):
        sub = sub[:-1]
    return sub.strip()


def _strip_shell_wrapping(words: list[str]) -> list[str]:
    """Снимает `(`/`{`/ключевые слова `do`/`then`/`else`/`!` спереди и
    `)`/`}` сзади — то, что осталось отдельными токенами после разбиения на
    подкоманды (`{ find / -name x; }` → токены `{ find / -name x` и `}`)."""
    while words and (words[0] in ("(", "{") or words[0] in _LEADING_KEYWORDS):
        words = words[1:]
    while words and words[-1] in (")", "}"):
        words = words[:-1]
    return words


def extract_command_substitutions(command: str) -> list[str]:
    """Достаёт содержимое `$( ... )` (с учётом вложенности) — `x=$(find /
    -name x)`, `echo $(find / -name x)`. Backtick-подстановка (`` `...` ``)
    не разбирается — не встретилась в проверке, оставлена как известная
    граница (см. README.md, «Что НЕ перехватывается»)."""
    subs: list[str] = []
    i = 0
    n = len(command)
    while i < n:
        if command[i : i + 2] == "$(":
            depth = 1
            j = i + 2
            start = j
            while j < n and depth > 0:
                if command[j] == "(":
                    depth += 1
                elif command[j] == ")":
                    depth -= 1
                j += 1
            subs.append(command[start : max(j - 1, start)])
            i = j
            continue
        i += 1
    return subs


def evaluate(command: str, cwd: str, powershell: bool = False) -> tuple[bool, str]:
    cwd = _norm(cwd or "/")
    for inner in extract_command_substitutions(command):
        blocked, reason = evaluate(inner, cwd, powershell)
        if blocked:
            return True, reason
    for sub in split_subcommands(command, powershell):
        sub = _strip_group_chars(sub)
        words = _strip_shell_wrapping(tokenize(sub, powershell))
        words = strip_wrappers(words)
        if not words:
            continue
        if os.path.basename(words[0]).lower() in ("cd", "pushd"):
            target = words[1] if len(words) > 1 else "~"
            cwd = resolve(target, cwd)
            continue
        result = check_subcommand(words, cwd)
        if result and result[0]:
            return True, result[1]
    return False, ""


# Токен в мегабайты валит shlex/наш разбор в квадратичное время и рискует
# упереться в таймаут хука на стороне Claude Code — грубый ранний выход
# дешевле, чем разбирать то, что никто руками не печатает.
_MAX_COMMAND_LEN = 50_000


def main() -> int:
    # Windows-консоль по умолчанию не UTF-8 (частая cp1251/cp866) — без
    # reconfigure русский текст в stderr либо превращается в мусор для
    # читающего как UTF-8, либо на локали без кириллицы (C/POSIX) валит
    # запись исключением UnicodeEncodeError. Кодировка stderr фиксируется
    # явно, а не зависит от локали хоста.
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # не смогли разобрать вход — не блокируем вслепую

    try:
        tool_name = payload.get("tool_name", "")
        if tool_name not in ("Bash", "PowerShell"):
            return 0

        tool_input = payload.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            return 0
        command = tool_input.get("command", "")
        if not command or not isinstance(command, str):
            return 0
        if len(command) > _MAX_COMMAND_LEN:
            return 0

        powershell = tool_name == "PowerShell"

        cwd = payload.get("cwd") or os.getcwd()
        if not isinstance(cwd, str):
            cwd = os.getcwd()

        blocked, reason = evaluate(command, cwd, powershell)
    except Exception:
        # Неожиданная форма входа (не тот тип поля, обрыв разбора и т.п.) —
        # fail-open, см. докстринг модуля. Не пробрасываем исключение выше:
        # трейсбек на stderr при незаблокированном коде возврата уже почти
        # не отличается от него же при штатном exit 0.
        return 0

    if blocked:
        try:
            sys.stderr.write(f"Заблокировано хуком block_wide_fs_search: {reason}.\n\n{SUGGESTION}\n")
        except Exception:
            pass
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
