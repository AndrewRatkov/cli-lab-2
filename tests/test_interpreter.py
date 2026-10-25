from unittest.mock import patch

import pytest

from interpreter.interpreter import Interpreter
from parser import Parser
from utils.session import Session


class InputExhausted(BaseException): ...


async def run_interpreter(lines):
    with patch("aioconsole.ainput", side_effect=[*lines, InputExhausted]):
        await Interpreter().run()


@pytest.mark.parametrize(
    "lines, expected",
    [
        (["exit"], ""),
        (["", 'echo "Hello, world!"', "exit"], "Hello, world!\n"),
        (["echo 'unclosed", "echo recovered", "exit"], "Unclosed quote\nrecovered\n"),
        (
            ["pwd unexpected", "echo recovered", "exit"],
            "Command exited with non-zero code 1\nrecovered\n",
        ),
    ],
    ids=["exit", "blank-input", "parser-error", "execution-error"],
)
async def test_interpreter_session(lines, expected, capsys):
    await run_interpreter(lines)
    assert capsys.readouterr().out == expected


async def test_assignment_survives_between_commands(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FILE", "before")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "example.txt").write_bytes(b"Some example text\n")
    await run_interpreter(["FILE=example.txt", "cat $FILE", "exit"])
    assert capsys.readouterr().out == "Some example text\n"


async def test_cd_survives_between_commands(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.delenv("OLDPWD", raising=False)
    target = tmp_path / "directory with spaces"
    target.mkdir()
    (target / "example.txt").write_bytes(b"hello\n")
    await run_interpreter(['cd "directory with spaces"', "pwd", "cat example.txt", "exit"])
    assert capsys.readouterr().out == str(target) + "\nhello\n"


async def test_unexpected_error_is_reported_and_loop_continues(capsys):
    exit_sequence = Parser(Session()).parse("exit")
    with patch(
        "interpreter.interpreter.Parser.parse", side_effect=[RuntimeError("boom"), exit_sequence]
    ):
        await run_interpreter(["anything", "exit"])
    assert capsys.readouterr().out == "Unexpected error occurred:\nboom\n"
