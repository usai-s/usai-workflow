# Backlog

**Только очередь: задачи, которые ещё не заведены.** Как только задача
стартовала — появились папка `docs/features/<id>/`, ветка и worktree — её
строка отсюда удаляется. Завершение задачи backlog не трогает вовсе:
что в работе — видно по веткам и `status.md`, что сделано — по `git log`.
Сводка по всем вопросам: `scripts/backlog.sh`.

Формат строки:

`- [ ] <id> — <суть> · epic:<эпик> · size:<F|S|M|L> · deps:<короткие id|-> · note:<чем важно | ->`

У ещё не начатой задачи вместо номера — литерал `NNN` (`feat-NNN-<slug>`):
номер присваивается при заведении ветки (`scripts/new-task.sh`), правила —
`docs/features/README.md`.

## Очередь

- [ ] tech-NNN-install-update-command — команда `update`: пересинхронизация файлов ядра по lock-файлу, отчёт что изменилось · epic:installer · size:M · deps:- · note:главный недостающий кусок жизненного цикла
- [ ] tech-NNN-npm-publish — публикация пакета в npm registry: npm-аккаунт человека, provenance, инструкция релиза (тег + npm publish) · epic:installer · size:S · deps:- · note:пока установка идёт через npx github:
- [ ] tech-NNN-installer-tests — автотесты bin/usai.js: конфликты, seed, requires, lock; прогон в CI · epic:installer · size:S · deps:- · note:сейчас движок проверяется только смоуком в verify
- [ ] tech-NNN-verify-v2-diff-routing — verify v2: классификация изменённых файлов и запуск только осмысленных проверок (движок в проекте-источнике) · epic:core · size:M · deps:- · note:убирает главное расхождение с исходным workflow
- [ ] tech-NNN-ci-github-actions — CI: workflow GitHub Actions, гоняющий scripts/verify.sh на PR · epic:ops · size:S · deps:- · note:сейчас зелёность держится на pre-push и дисциплине
- [ ] tech-NNN-branch-protection — защита main на GitHub: squash-only, обязательный PR и зелёный CI, автоудаление веток · epic:ops · size:F · deps:tech-NNN-ci-github-actions · note:PR #1 был влит merge-коммитом — конвенция требует squash
- [ ] mod-NNN-stack-module-backend-dotnet — stack-модуль backend-dotnet: конвенции, ADR-пресеты (миграции явно, ошибки-исключения и т.п.), строки verify.config · epic:modules · size:M · deps:- · note:первый образец stack-модуля, источник — проект-источник
- [ ] mod-NNN-stack-module-frontend-react — stack-модуль frontend-react: конвенции, канон состояний, строки verify.config · epic:modules · size:M · deps:mod-NNN-stack-module-backend-dotnet · note:после образца backend
- [ ] tech-NNN-live-check-codex-adapter — проверить adapter-codex на живом Codex: skill, профили, hook trust · epic:adapters · size:S · deps:- · note:адаптер портирован, но живьём не запускался
- [ ] tech-NNN-live-check-claude-adapter — прогнать /feature на живом Claude Code в тестовом проекте · epic:adapters · size:S · deps:- · note:команды и агенты после генерализации живьём не запускались
- [ ] doc-NNN-english-localization — английская локализация ядра (язык артефактов — параметр установки) · epic:l10n · size:L · deps:- · note:расширяет аудиторию публичного репозитория
