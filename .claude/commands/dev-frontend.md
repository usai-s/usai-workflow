---
description: Этапы 6–7 — frontend-разработка и frontend-QA
argument-hint: <id фичи>
---

Фича: $ARGUMENTS

1. Проверь, что `api-contract.md` существует (frontend может идти параллельно
   backend-QA, но не раньше фиксации контракта).
2. Запусти субагента **frontend-developer** (этап 6).
3. Затем субагента **qa-engineer** с указанием «frontend» (этап 7) — отдельным
   вызовом, чистый контекст.
4. Дефекты-блокеры → верни frontend-developer'у; максимум 2 цикла, дальше
   эскалация человеку. По завершении сообщи итог и путь к qa.md (раздел Frontend).
