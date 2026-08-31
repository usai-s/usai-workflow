#!/bin/sh
# Сводка по проекту: что в работе, что в очереди, что занято, что сделано.
#
# Бэклог хранит только очередь незаведённых задач; остальное выводится из
# веток, папок фич и истории — там, где оно и так живёт. Дублировать это в
# общем файле стоило конфликтов слияния при каждом старте и завершении.
#
#   scripts/backlog.sh          сводка
#   scripts/backlog.sh --ids    только занятые номера (для проверки нумерации)

set -eu

# Корень ТЕКУЩЕГО worktree, а не главного репозитория: --git-common-dir
# увёл бы в основной чекаут и читал чужой backlog.md.
cd "$(git rev-parse --show-toplevel)"

taken_ids() {
    {
        ls docs/features 2>/dev/null | grep -oE "^[a-z]+-[0-9]{3}" || true
        git branch --all --format="%(refname:short)" | grep -oE "[a-z]+/[0-9]{3}" | tr "/" "-" || true
        grep -oE "^- \[[ x]\] [a-z]+-[0-9]{3}" docs/backlog.md 2>/dev/null | grep -oE "[a-z]+-[0-9]{3}$" || true
    } | sort -u
}

if [ "${1:-}" = "--ids" ]; then
    taken_ids
    exit 0
fi

printf '\n=== В РАБОТЕ (ветки задач) ===\n\n'
found=0
for branch in $(git branch --format="%(refname:short)" | grep -E "^(feat|bug|hot|tech|mod|doc)/[0-9]{3}-"); do
    found=1
    id=$(printf '%s' "$branch" | sed "s|/|-|")
    status="docs/features/$id/status.md"

    stage=""
    size=""
    epic=""
    if [ -f "$status" ]; then
        stage=$(grep -m1 "^- stage:" "$status" | sed "s/^- stage: *//")
        size=$(grep -m1 "^- size:" "$status" | sed "s/^- size: *//")
        epic=$(grep -m1 "^- epic:" "$status" | sed "s/^- epic: *//")
    else
        # status.md живёт в своей ветке — из main его не видно
        stage=$(git show "$branch:docs/features/$id/status.md" 2>/dev/null | grep -m1 "^- stage:" | sed "s/^- stage: *//" || echo "?")
        size=$(git show "$branch:docs/features/$id/status.md" 2>/dev/null | grep -m1 "^- size:" | sed "s/^- size: *//" || echo "?")
    fi

    [ -n "$stage" ] || stage="?"
    [ -n "$size" ] || size="?"
    [ -n "$epic" ] || epic="-"
    ahead=$(git rev-list --count main.."$branch" 2>/dev/null || echo "?")
    printf '  %-30s %-17s size:%-2s stage:%-19s +%s\n' "$branch" "$epic" "$size" "$stage" "$ahead"
done
[ "$found" = 0 ] && printf '  нет активных веток задач\n'

printf '\n=== В ОЧЕРЕДИ (docs/backlog.md) ===\n\n'
queue=$(grep -cE "^- \[ \]" docs/backlog.md 2>/dev/null || echo 0)
if [ "$queue" = "0" ]; then
    printf '  очередь пуста\n'
else
    epics=$(grep -E "^- \[ \]" docs/backlog.md | grep -oE "epic:[^ ]*" | cut -d: -f2 | sort -u)
    [ -n "$epics" ] || epics="-"
    for epic in $epics; do
        printf '  [%s]\n' "$epic"
        grep -E "^- \[ \]" docs/backlog.md | grep -F "epic:$epic " | while read -r line; do
            id=$(printf '%s' "$line" | grep -oE "[a-z]+-[0-9]{3}-[a-z0-9-]+" | head -1)
            size=$(printf '%s' "$line" | grep -oE "size:[FSML]" | cut -d: -f2)
            deps=$(printf '%s' "$line" | grep -oE "deps:[^·]*" | cut -d: -f2 | sed "s/ *$//")
            printf '    %-40s size:%-2s deps:%s\n' "$id" "$size" "$deps"
        done
    done
fi

printf '\n=== ЗАВЕРШЕНО (stage: complete) ===\n\n'
done_count=0
for dir in docs/features/*/; do
    [ -f "$dir/status.md" ] || continue
    grep -q "^- stage: complete" "$dir/status.md" || continue
    done_count=$((done_count + 1))
done
printf '  %s задач; список: grep -l "stage: complete" docs/features/*/status.md\n' "$done_count"

printf '\n=== НОМЕРА ===\n\n'
for prefix in feat bug hot tech mod doc; do
    last=$(taken_ids | grep -oE "^$prefix-[0-9]{3}$" | grep -oE "[0-9]{3}$" | sort -n | tail -1)
    [ -n "${last:-}" ] || continue
    next=$(printf '%03d' $(( 10#$last + 1 )))
    printf '  %-5s занято до %s, следующий %s\n' "$prefix" "$last" "$next"
done

printf '\n'
