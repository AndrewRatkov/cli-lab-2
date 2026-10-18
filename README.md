# HW1
![CI](https://github.com/ISArchitec/HW1/actions/workflows/ci.yml/badge.svg)

Homework 1

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

## Архитектура

Основным объектом, отвечающим за работу всего приложения является представитель класса Interpreter.

Разбор входной строки реализуется представителем класса Parser, который с помощью
вспомогательных объектов конструирует AST.

AST представляет из себя список предложений (SentenceSequence), соединённых пайпами. Каждое предложение представляет из себя непустой набор присваиваний и следующих за ними слов. Первое слово означает команду, остальное —
её аргументы.

SentenceSequence отвечает за соединение команд пайпами (Pipe) в правильном порядке и их запуск методом execute().

В процессе работы поддерживается глобальная сессия (Session), содержащая значения переменных, которые используются в подстановках. Если одно или несколько присваиваний встречаются перед набором слов, то они используются только в качестве переменных окружения в этих командах, в противном случае они запоминаются в глобальной сессии.
