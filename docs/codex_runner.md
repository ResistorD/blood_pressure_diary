# Codex Runner (Local)

Минимальный локальный набор для запуска задач Codex из файла без ручной оркестрации.

## Быстрый старт
1. Сохраните задачу в файл, например `codex/prompts/my_task.txt`.
2. Запустите:

```bash
./scripts/codex_runner/run_codex_task.sh codex/prompts/my_task.txt
```

## Поддерживаемые команды

```bash
./scripts/codex_runner/run_codex_task.sh [--run-tests] [--py-compile] [--name <run-name>] [--dry-run] <prompt-file>
```

Опции:
- `--run-tests`: после работы Codex запускает `python -m pytest -q` и сохраняет вывод.
- `--py-compile`: запускает `python -m py_compile` по изменённым Python-файлам.
- `--name <run-name>`: имя прогона в каталоге `codex/runs/`.
- `--dry-run`: создаёт run-dir и артефакты без реального вызова Codex.

## Неинтерактивный запуск Codex
Раннер использует:

```bash
codex exec -C <repo_root> --output-last-message <run_dir>/codex_last_message.txt -
```

Промпт передаётся через stdin из `prompt.txt`.

Если `codex exec` недоступен, используется простой fallback через `codex` (описан в summary файла прогона).

## Структура run-dir
Для каждого запуска создаётся каталог:

```text
codex/
  prompts/
  runs/YYYY-MM-DD_HHMMSS_<name>/
  templates/
```

Можно по-прежнему использовать старые пути (`prompts/...`, `codex_runs/...`) вручную, но дефолтные примеры и новые запуски ориентированы на структуру `codex/...`.

Типичный состав:
- `prompt.txt`
- `summary.txt`
- `codex_stdout.txt`
- `codex_stderr.txt`
- `codex_last_message.txt` (если создан)
- `git_status.txt`
- `changed_files.txt`
- `git_diff_stat.txt`
- `git_diff.patch`
- `collect_stdout.txt`
- `collect_stderr.txt`
- `pytest.txt` / `pytest_status.txt` (если `--run-tests`)
- `py_compile.txt` / `py_compile_status.txt` (если `--py-compile`)

## Что всё ещё вручную
- Просмотреть `summary.txt` и нужные артефакты.
- Вставить `summary.txt` (и при необходимости `git_diff_stat.txt` / `codex_last_message.txt`) обратно в чат.
