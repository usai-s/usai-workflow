---
description: Этапы 8–10 — code review, gate-3, PR и Complete
argument-hint: <id фичи>
---

Фича: $ARGUMENTS

0. Если `size: F` — code review и QA не запускаются: иди сразу к пункту 3
   по `docs/ai-workflow/stages/f-route.md`.
1. Проверь в status.md, что QA пройдено (блокеров нет).
2. Запусти субагента **code-reviewer** (этап 8). Для L-фич — дополнительно
   ВТОРОГО code-reviewer'а отдельным вызовом только на security-чек-лист
   (см. этап 8 в 06-review-complete.md). Blocker/major-замечания → верни
   соответствующему разработчику, повторный QA по затронутому,
   максимум 2 круга.
3. Подготовь для человека пакет gate-3 по
   `docs/ai-workflow/stages/06-review-complete.md`: summary, как запустить,
   что проверить руками. Дождись вердикта, запиши в status.md.
4. После `gate-3: approved`: rebase на main, финальный прогон тестов/линтеров,
   PR по формату из инструкции этапа. После merge — шаг Complete
   (backlog → Done, status.md → complete, новые задачи → backlog с литералом
   `NNN` вместо цифр — номер даётся при заведении ветки).
