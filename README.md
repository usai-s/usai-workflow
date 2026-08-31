# usai-workflow

Переносимый AI workflow для разработки через агентов (Claude Code, Codex и
др.): пайплайн этапов с human gates, роутинг задач по типу и размеру
(F/S/M/L), состояние в файлах вместо контекста чата, ревью и QA в чистых
сессиях. Выращен на реальном проекте, вычищен от его специфики и разложен на
устанавливаемые модули.

## Установка

Требуется Python ≥ 3.11 (только стандартная библиотека).

```bash
git clone https://github.com/usai-s/usai-workflow.git
python usai-workflow/install.py --target /путь/к/вашему/проекту
```

Установщик спросит, какие модули ставить, скопирует файлы и запишет
`.usai-workflow.lock` (версия + модули + sha256 файлов). Без вопросов:

```bash
python usai-workflow/install.py --target /путь/к/проекту --all --yes
python usai-workflow/install.py --target /путь/к/проекту --modules adapter-claude --yes
python usai-workflow/install.py --list       # список модулей
```

Существующий файл с другим содержимым останавливает установку до первой
записи; `--force` перезаписывает. **Seed-файлы** (`AGENTS.md`, `CLAUDE.md`,
`docs/backlog.md`, `scripts/verify.config.sh`) — проектные заготовки:
создаются только если их ещё нет, ваши правки в них не перетираются.

После установки:

1. Заполните слоты `<...>` в `AGENTS.md` — описание проекта, стек, команды,
   каталог legacy-системы (если есть).
2. Объявите проверки проекта в `scripts/verify.config.sh`.
3. Заполните заготовки `docs/conventions/{backend,frontend}.md` под свой
   стек (git.md уже пригоден как есть) — пайплайн ссылается на них как на
   источник правил кода.
4. Включите git-хуки: `git config core.hooksPath .githooks` (pre-commit —
   защита main и формат ветки, commit-msg — формат заголовка, pre-push —
   `scripts/verify.sh`).
5. Проверьте согласованность адаптеров: `python scripts/validate-ai-workflow.py`.

## Что внутри

| Каталог | Что это |
|---------|---------|
| `core/` | Ядро (ставится всегда): `docs/ai-workflow/` — пайплайн, роутинг, этапы; `docs/features/README.md` — формат задач и `status.md`; `docs/adr/` + шаблоны артефактов; `scripts/` — new-task, backlog, verify (+ PowerShell-обёртки) |
| `modules/adapter-claude/` | Адаптер Claude Code: `/feature` и команды этапов, субагенты ролей с уровнями моделей, PreToolUse-хук против широкого поиска по диску (94 оффлайн-теста) |
| `modules/adapter-codex/` | Адаптер Codex: skill `$feature`, профили ролей `.codex/agents`, hook с той же policy (Windows-адаптер + тесты). Требует adapter-claude |
| `install.py` | Движок установки — модулей не знает, читает их манифесты |

Суть процесса (подробно — `core/files/docs/ai-workflow/README.md`):

- задача классифицируется по типу (`feat`/`bug`/`hot`/`tech`/`mod`/`doc`) и
  размеру (F/S/M/L) — от этого зависит маршрут и число гейтов;
- этапы: legacy-анализ (опционально) → бизнес-аналитика → адверсариальное
  ревью требований → **gate-1** → UX-дизайн → **gate-2** → backend (план →
  api-contract → код) → QA → frontend → QA → code review → **gate-3** → PR;
- состояние каждой задачи — в `docs/features/<id>/status.md`; любой агент
  продолжает работу с любого этапа, прочитав файлы;
- merge в main делает только человек.

## Свой модуль

Модуль = каталог в `modules/` с манифестом и файлами:

```
modules/<id>/
├── module.toml     # id, title, description, question, requires, seed
└── files/          # зеркалит раскладку целевого проекта
```

`requires` — зависимости от других модулей; `seed` — список целевых путей,
которые создаются только при отсутствии (проектные заготовки). Движок
запрещает двум модулям владеть одним файлом.

## Дорожная карта

Очередь задач — [docs/backlog.md](docs/backlog.md). Крупное: `install.py
update`, stack-модули с ADR-пресетами, verify v2 (запуск проверок по классу
изменённых файлов), CI, английская локализация ядра.

Язык артефактов — русский (осознанное решение проекта-источника; язык — слот
`AGENTS.md`, самим документам локализация в планах).

## Лицензия

[MIT](LICENSE).
