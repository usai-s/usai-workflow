# tech-001-port-codex-and-conventions

- type: tech
- size: M
- branch: tech/001-port-codex-and-conventions
- stage: 04-backend
- legacy: none
- epic: content
- gates: gate-3

## Gates

gate-3: pending

## Plan

1. Модуль adapter-codex: .codex/ (агенты, config, hooks) + .agents/skills
   из проекта-источника, генерализация от его специфики.
2. Ядро: scripts/validate-ai-workflow.py (адаптирован: проверяет только
   установленные адаптеры), .githooks/ (pre-commit, commit-msg, pre-push),
   docs/conventions/git.md (генерализован) + заготовки backend/frontend.
3. Проводка: seeds в core/module.toml, README, VERSION 0.2.0, самоустановка
   (self-sync), verify + validate в конфиге проверок проекта.
4. Бэклог: очередь оставшихся работ в docs/backlog.md.
Проверка: scripts/verify.sh (включая adapters и self-sync).

## Log

- 2026-08-31 [new-task] задача заведена, worktree C:/Users/khamb/Workspace/usa-s/usai-workflow-worktrees/tech-001-port-codex-and-conventions
- 2026-08-31 [orchestrator] standing approval человеком в чате («ты многое не
  перенёс. сделай. так же составь бэклог») — маршрут M по механике
  облегчённого docs-only цикла (правится только контент/скрипты workflow,
  runtime-кода в репозитории нет); gate-3 остаётся за человеком

## Notes

