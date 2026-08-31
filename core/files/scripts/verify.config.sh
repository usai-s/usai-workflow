# Проверки проекта для scripts/verify.sh — ЗАГОТОВКА (seed), заполните под
# свой стек. Формат: по строке "<метка> :: <команда>"; команда выполняется
# `sh -c` из корня worktree. Держите набор точным: лишние проверки жгут
# время каждой задачи, недостающие пропускают дефекты.
#
# Примеры для типичных стеков (раскомментируйте и поправьте):
#
#   backend  :: dotnet build MySolution.sln --nologo -v q
#   tests    :: dotnet test MySolution.sln --no-build --nologo -v q
#   frontend :: cd frontend && npm run build
#   lint     :: cd frontend && npm run lint
#   shell    :: for f in scripts/*.sh; do sh -n "$f" || exit 1; done

verify_checks() {
    cat <<'CHECKS'
shell-syntax :: for f in scripts/*.sh; do sh -n "$f" || exit 1; done
CHECKS
}
