---
description: Этап 2 — адверсариальное ревью spec.md + подготовка gate-1
argument-hint: <id фичи>
---

Фича: $ARGUMENTS

1. Запусти субагента **requirements-reviewer** для `docs/features/$ARGUMENTS/`.
2. Когда он закончит — покажи человеку его summary и открытые вопросы,
   попроси вердикт по gate-1 и запиши его в status.md.
