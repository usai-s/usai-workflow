# Проверки репозитория usai-workflow для scripts/verify.sh.
# Формат: по строке "<метка> :: <команда>", команда выполняется `sh -c`
# из корня worktree.

verify_checks() {
    cat <<'CHECKS'
py-syntax :: python -m py_compile install.py scripts/validate-ai-workflow.py .claude/hooks/block_wide_fs_search.py .claude/hooks/tests/run_cases.py
shell-syntax :: for f in scripts/*.sh core/files/scripts/*.sh .githooks/* core/files/.githooks/*; do sh -n "$f" || exit 1; done
adapters :: python scripts/validate-ai-workflow.py >/dev/null
hook-tests :: python .claude/hooks/tests/run_cases.py >/dev/null
install-smoke :: t=$(mktemp -d) && python install.py --target "$t" --all --yes >/dev/null && rm -rf "$t"
self-sync :: python install.py --target . --all --yes --dry-run | grep -q "к записи: 0"
CHECKS
}
