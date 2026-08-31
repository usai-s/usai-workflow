#!/bin/sh
# Единая точка проверки проекта: прогоняет проверки, объявленные проектом в
# scripts/verify.config.sh, и возвращает ненулевой код при первом же провале
# (все проверки при этом выполняются — отчёт полный).
#
#   scripts/verify.sh           прогнать все проверки
#   scripts/verify.sh --list    показать список без запуска
#
# Формат конфига: функция verify_checks печатает по строке на проверку —
#   <метка> :: <команда>
# Команда выполняется через `sh -c` из корня worktree. Пустые строки и
# строки с # игнорируются.
#
# Это v1-движок: набор проверок статичен. Классификация изменённых файлов и
# запуск только осмысленных для diff проверок — задел на следующую версию.

set -eu

cd "$(git rev-parse --show-toplevel)"

config="scripts/verify.config.sh"
[ -f "$config" ] || {
    printf 'verify: нет %s — создайте его (заготовку ставит usai-workflow).\n' "$config" >&2
    exit 1
}

# shellcheck disable=SC1090
. "$config"

command -v verify_checks >/dev/null 2>&1 || type verify_checks >/dev/null 2>&1 || {
    printf 'verify: %s не определяет функцию verify_checks.\n' "$config" >&2
    exit 1
}

checks=$(verify_checks | grep -vE '^[[:space:]]*(#|$)' || true)
[ -n "$checks" ] || {
    printf 'verify: verify_checks не объявил ни одной проверки.\n' >&2
    exit 1
}

if [ "${1:-}" = "--list" ]; then
    printf '%s\n' "$checks"
    exit 0
fi

# Пайп порождает subshell — итог провалов передаётся через временный файл.
failed=$(mktemp)
trap 'rm -f "$failed"' EXIT

printf '%s\n' "$checks" | while IFS= read -r line; do
    label=${line%% :: *}
    cmd=${line#* :: }
    printf '\n=== %s ===\n+ %s\n' "$label" "$cmd"
    sh -c "$cmd" || { printf 'verify: ПРОВАЛ: %s\n' "$label" >&2; printf '%s ' "$label" >> "$failed"; }
done

if [ -s "$failed" ]; then
    printf '\nverify: ПРОВАЛ — %s\n' "$(cat "$failed")" >&2
    exit 1
fi
printf '\nverify: OK\n'
