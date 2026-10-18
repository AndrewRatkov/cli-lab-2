# HW1
![CI](https://github.com/ISArchitec/HW1/actions/workflows/ci.yml/badge.svg)

Homework CLI

Требуется Python 3.13.

## Запуск тестов

```bash
python -m pip install -r requirements.txt
python -m pytest --cov
```

## Линтеры и проверка типов

Используются [ruff](https://docs.astral.sh/ruff/) (линтер + форматтер) и
[pyright](https://github.com/microsoft/pyright). Настройки — в `pyproject.toml`,
хуки — в `.pre-commit-config.yaml`.

```bash
python -m pip install -r requirements-dev.txt
pre-commit install          # хуки будут запускаться при каждом коммите
pre-commit run --all-files  # ручной прогон по всему проекту
```

Отдельно:

```bash
ruff check --fix .
ruff format .
pyright
```

В CI те же проверки выполняются в job `lint`.

## Coverage

```bash
pip install coverage
coverage run -m pytest
coverage report -m
coverage html
```
