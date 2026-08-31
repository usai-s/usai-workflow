#!/bin/sh
# Заводит задачу: номер, ветку, worktree и папку docs/features/<id>/.
#
# Использование:
#   scripts/new-task.sh <префикс> <slug> "<суть задачи>" [размер] [epic]
#
#   scripts/new-task.sh feat permit-application-form "Форма подачи заявки" L
#   scripts/new-task.sh bug quota-rounding "Неверное округление остатка квоты" S
#
# Префиксы: feat, bug, hot, tech, mod, doc — см. docs/features/README.md.
# Размер: F | S | M | L, по умолчанию M.
# Epic:   к чему относится задача (module/orders, platform/db, workflow).
#         По умолчанию берётся из строки очереди, иначе "-".
#
# Скрипт ничего не коммитит: созданные файлы остаются в новом worktree,
# коммит — за оркестратором или человеком.

set -eu

die() {
    printf '\n%s\n\n' "$1" >&2
    exit 1
}

usage() {
    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

case "${1:-}" in
    ''|-h|--help) usage 0 ;;
esac

prefix=$1
slug=${2:-}
summary=${3:-}
size=${4:-M}
epic=${5:-}

# --- Проверки аргументов ------------------------------------------------------
case "$prefix" in
    feat|bug|hot|tech|mod|doc) ;;
    *) die "Неизвестный префикс '$prefix'. Допустимы: feat, bug, hot, tech, mod, doc." ;;
esac

[ -n "$slug" ] || die "Не задан slug. Пример: scripts/new-task.sh bug quota-rounding \"Суть\" S"
[ -n "$summary" ] || die "Не задана суть задачи (третий аргумент)."

printf '%s' "$slug" | grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$' \
    || die "Slug '$slug' не kebab-case: только строчная латиница, цифры и дефисы."

case "$size" in
    F|S|M|L) ;;
    *) die "Размер '$size' не из F|S|M|L." ;;
esac

# bugfix/hotfix не бывают F: у бага есть тест, падавший до фикса, то есть
# изменение поведения по определению (stages/f-route.md).
if [ "$size" = 'F' ] && { [ "$prefix" = 'bug' ] || [ "$prefix" = 'hot' ]; }; then
    die "Размер F недопустим для префикса '$prefix' — минимум S (f-route.md)."
fi

# --- Корень основного репозитория (скрипт может запускаться из worktree) ------
common_dir=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) \
    || die "Не git-репозиторий."
repo=$(dirname "$common_dir")
backlog="$repo/docs/backlog.md"

[ -f "$backlog" ] || die "Не найден $backlog."

# --- Следующий свободный номер -------------------------------------------------
# Три источника, максимум по всем: backlog (в т.ч. Done), существующие папки
# фич и ветки. Ветки важны отдельно: номер, занятый в незамерженной ветке,
# в backlog основной ветки ещё не виден.
# Источники 2 и 3 обходятся по ВСЕМ веткам (TODO из tech-012 закрыт в
# tech-040): папка фичи или строка backlog в незамерженной ветке из рабочей
# копии не видна, и без обхода две сессии могли взять один номер. Обход
# ограничен refs/heads и refs/remotes намеренно — иначе попадает refs/stash.
all_refs=$(git -C "$repo" for-each-ref --format='%(refname:short)' refs/heads refs/remotes 2>/dev/null)
numbers=$(
    {
        echo "$all_refs" | grep -oE "${prefix}/[0-9]{3}" | tr '/' '-' || true
        for ref in $all_refs; do
            git -C "$repo" ls-tree --name-only "$ref:docs/features" 2>/dev/null                 | grep -oE "^${prefix}-[0-9]{3}" || true
            git -C "$repo" show "$ref:docs/backlog.md" 2>/dev/null                 | grep -oE "${prefix}-[0-9]{3}" || true
        done
        ls "$repo/docs/features" 2>/dev/null | grep -oE "^${prefix}-[0-9]{3}" || true
        grep -oE "${prefix}-[0-9]{3}" "$backlog" 2>/dev/null || true
    } | grep -oE '[0-9]{3}$' | sort -n
)

# Задача могла быть заранее поставлена в очередь под своим номером — тогда
# берём его, а не выдаём новый: иначе зарезервированный номер осиротеет.
# Если задача стояла в очереди — забираем оттуда и epic, чтобы не вводить руками.
if [ -z "$epic" ]; then
    epic=$(grep -oE "^- \[ \] ${prefix}-[0-9]{3}-${slug} .*" "$backlog" 2>/dev/null |
           grep -oE "epic:[^ ·]*" | head -1 | cut -d: -f2 || true)
fi
[ -n "$epic" ] || epic="-"

queued=$(grep -oE "^- \[ \] ${prefix}-[0-9]{3}-${slug}([ ]|$)" "$backlog" 2>/dev/null |
         grep -oE "[0-9]{3}" | head -1 || true)

last=$(printf '%s
' "$numbers" | tail -n 1)
# 10# — иначе номер с ведущим нулём читается как восьмеричный, и 008/009
# роняют арифметику.
if [ -n "${queued:-}" ]; then
    next=$queued
    printf 'Задача найдена в очереди backlog под номером %s — беру его.
' "$next"
else
    next=$(printf '%03d' $(( 10#${last:-0} + 1 )))
fi

id="${prefix}-${next}-${slug}"
branch="${prefix}/${next}-${slug}"
worktree="$(dirname "$repo")/$(basename "$repo")-worktrees/$id"

[ -e "$worktree" ] && die "Каталог $worktree уже существует."

# --- Тип, стартовый этап и гейты ------------------------------------------------
case "$prefix" in
    feat) type=feature; stage=01-business-analysis ;;
    mod)  type=module;  stage=00-legacy-analysis ;;
    doc)  type=docs;    stage=00-legacy-analysis ;;
    bug)  type=bugfix;  stage=04-backend ;;
    hot)  type=hotfix;  stage=04-backend ;;
    tech) type=tech;    stage=04-backend ;;
esac

# F- и S-маршруты: спека и дизайн не пишутся, значит у первых двух гейтов нет
# предмета — они не появляются в status.md вовсе. Агент объявляет применимость
# (поле gates), значение гейта ставит только человек.
if [ "$size" = 'F' ] || [ "$size" = 'S' ] || [ "$prefix" = 'bug' ] || [ "$prefix" = 'hot' ] || [ "$prefix" = 'tech' ]; then
    gates='gate-3'
    gate_lines='gate-3: pending'
    stage=04-backend
else
    gates='gate-1, gate-2, gate-3'
    gate_lines='gate-1: pending
gate-2: pending
gate-3: pending'
fi

# --- Worktree от свежего main ---------------------------------------------------
printf 'Задача:  %s\nВетка:   %s\nWorktree: %s\n\n' "$id" "$branch" "$worktree"

mkdir -p "$(dirname "$worktree")"
git -C "$repo" worktree add "$worktree" -b "$branch" main

feature_dir="$worktree/docs/features/$id"
mkdir -p "$feature_dir"

today=$(date +%Y-%m-%d)

cat > "$feature_dir/status.md" <<STATUS
# $id

- type: $type
- size: $size
- branch: $branch
- stage: $stage
- legacy: none
- epic: $epic
- gates: $gates

## Gates

$gate_lines

## Plan

<!-- S/M: план реализации 3–10 строк. L: см. plan-backend.md / plan-frontend.md -->

## Log

- $today [new-task] задача заведена, worktree $worktree

## Notes

STATUS

# --- Задача уходит из очереди --------------------------------------------------
# Backlog хранит только незаведённые задачи. С этого момента состояние живёт в
# status.md, поэтому строку из очереди убираем, если она там была.
python - "$worktree/docs/backlog.md" "$id" <<'PY'
import sys, pathlib

path, task_id = sys.argv[1:3]
p = pathlib.Path(path)
if not p.exists():
    sys.exit(0)

lines = p.read_text(encoding='utf-8').splitlines(keepends=True)
kept = [l for l in lines if not l.startswith("- [ ] " + task_id)]
if len(kept) != len(lines):
    p.write_text("".join(kept), encoding='utf-8', newline=chr(10))
    print("  строка задачи убрана из очереди backlog")
PY

printf '\nГотово. Дальше:\n'
printf '  1. Открой сессию агента с рабочим каталогом %s\n' "$worktree"
printf '  2. Проверь и закоммить docs/features/%s/status.md и docs/backlog.md\n' "$id"
printf '  3. По завершении: git worktree remove %s\n\n' "$worktree"
