# tech-002-npm-installer

- type: tech
- size: M
- branch: tech/002-npm-installer
- stage: 04-backend
- legacy: none
- epic: installer
- gates: gate-3

## Gates

gate-3: pending

## Plan

1. bin/usai.js — Node-движок (>=18, без зависимостей), паритет с install.py:
   list/dry-run/modules/all/yes/force, диалог, seeds, конфликты до записи,
   lock c sha256. package.json c bin → npx github:usai-s/usai-workflow.
2. Манифесты module.toml → module.json (JSON парсится без зависимостей и в
   Node, и в Python).
3. Удалить install.py и VERSION (версия теперь в package.json).
4. Правка ссылок: README, AGENTS.md, verify.config (js-syntax, manifests,
   smoke/self-sync через node), бэклог (+задача npm-publish).
Проверка: scripts/verify.sh; npx из GitHub — после merge (задача в бэклоге).

## Log

- 2026-08-31 [new-task] задача заведена, worktree C:/Users/khamb/Workspace/usa-s/usai-workflow-worktrees/tech-002-npm-installer

## Notes

