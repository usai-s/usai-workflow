# Проверки репозитория usai-workflow для scripts/verify.sh.
# Формат: по строке "<метка> :: <команда>", команда выполняется `sh -c`
# из корня worktree.

verify_checks() {
    cat <<'CHECKS'
js-syntax :: node --check bin/usai.js
py-syntax :: python -m py_compile scripts/validate-ai-workflow.py .claude/hooks/block_wide_fs_search.py .claude/hooks/tests/run_cases.py
manifests :: node -e "for (const f of ['core/module.json','modules/adapter-claude/module.json','modules/adapter-codex/module.json']) JSON.parse(require('fs').readFileSync(f,'utf8')); JSON.parse(require('fs').readFileSync('package.json','utf8'))"
shell-syntax :: for f in scripts/*.sh core/files/scripts/*.sh .githooks/* core/files/.githooks/*; do sh -n "$f" || exit 1; done
adapters :: python scripts/validate-ai-workflow.py >/dev/null
hook-tests :: python .claude/hooks/tests/run_cases.py >/dev/null
install-smoke :: t=$(mktemp -d) && node bin/usai.js --target "$t" --all --yes >/dev/null && rm -rf "$t"
self-sync :: node bin/usai.js --target . --all --yes --dry-run | grep -q "к записи: 0"
CHECKS
}
