@AGENTS.md

## Claude Code

- Оркестрация фич: команда `/feature <описание задачи>` — она классифицирует
  задачу и ведёт по пайплайну из docs/ai-workflow/README.md.
- Этапы по отдельности: /analyze, /review-requirements, /design, /dev-backend,
  /dev-frontend, /qa, /ship.
- Субагенты в .claude/agents/ уже привязаны к этапам и уровням моделей —
  используй их через Task tool, не выполняй ревью/QA в основном контексте.
