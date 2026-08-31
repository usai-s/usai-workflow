---
description: Этапы 0–1 — legacy-анализ и бизнес-аналитика для фичи
argument-hint: <id фичи или описание>
---

Для задачи: $ARGUMENTS

1. Прочитай `docs/features/<id>/status.md` (или создай фичу, как описано в
   `docs/features/README.md`).
2. Если требуется legacy-анализ (см. routing.md, правила пропуска) и
   `docs/legacy/<модуль>.md` ещё нет — запусти субагента **legacy-analyst**.
3. Затем запусти субагента **business-analyst** для этапа 1.
4. Покажи результат: путь к spec.md и список открытых вопросов.
