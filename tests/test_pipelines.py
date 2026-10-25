"""Real parser -> sentence sequence -> commands -> Pipe integration tests."""

import asyncio
import os
import sys

import pytest

from parser import Parser
from tests.helpers import MemoryStream, cleanup_tasks
from utils.exception import ExecutionError

PIPELINE_TIMEOUT = 3
missing_eof = pytest.mark.xfail(
    strict=True,
    raises=TimeoutError,
    reason="Pipe has no EOF and SentenceSequence does not close stage outputs",
)


def python_stage(script):
    assert "'" not in script
    executable = sys.executable.replace("\\", "/")
    return f"\"{executable}\" -c '{script}'"


@pytest.fixture
async def run_pipeline(monkeypatch, session):
    output = MemoryStream()
    monkeypatch.setattr("sentence.sentence_sequence.Console", lambda: output)

    async def run(source):
        await asyncio.wait_for(Parser(session).parse(source).execute(), PIPELINE_TIMEOUT)
        return output.buffer.getvalue()

    async with cleanup_tasks():
        yield run


@pytest.mark.parametrize(
    "source, expected",
    [
        pytest.param("echo hello | cat", "hello\n", id="copy-and-finish"),
        pytest.param(
            'echo -e "skip\\nHIT\\ncontext\\nend" | grep -wi -A 1 hit | wc -l',
            "2\n",
            id="grep-matching-and-context",
        ),
        pytest.param("echo 123 | wc", "1 1 4\n", id="counts-after-eof"),
        pytest.param("echo -n | cat | wc -c", "0\n", id="empty-three-stage"),
        pytest.param("echo -n abc | cat | wc -lc", "0 3\n", id="no-final-newline"),
        pytest.param('echo "a|b" | cat | wc -w', "1\n", id="quoted-pipe-is-data"),
        pytest.param(
            'echo -e "one\\n\\n\\ntwo" | cat -s | wc -lw',
            "3 2\n",
            id="squeeze-blank-lines-before-counting",
        ),
        pytest.param("echo abc | wc -c | cat -n", "     1\t4\n", id="format-count-result"),
    ],
)
async def test_builtin_pipelines(run_pipeline, source, expected):
    assert await run_pipeline(source) == expected


async def test_example_file_pipeline(run_pipeline, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "example.txt").write_bytes(b"Some example text\n")
    assert await run_pipeline("cat example.txt | wc") == "1 3 18\n"


@pytest.mark.parametrize("source", ["cd target | pwd", "echo hello | cd target"])
async def test_cd_in_pipeline_does_not_change_directory(
    run_pipeline, tmp_path, monkeypatch, source
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "target").mkdir()
    with pytest.raises(ExecutionError) as raised:
        await run_pipeline(source)
    assert raised.value.code == 1
    assert os.getcwd() == str(tmp_path)


async def test_file_pipeline_crosses_queue_capacity(run_pipeline, tmp_path):
    path = tmp_path / "many lines.txt"
    path.write_bytes(b"a b\n" * 250000)
    assert await run_pipeline(f'cat "{path.as_posix()}" | cat | wc -lw') == "250000 500000\n"


async def test_substitution_and_literal_pipe_in_pipeline(run_pipeline, session):
    session.set("TEXT", "one | two")
    assert await run_pipeline('echo "$TEXT" | cat | wc -w') == "3\n"


async def test_builtin_external_builtin_pipeline(run_pipeline):
    stage = python_stage("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read().upper())")
    assert await run_pipeline(f"echo hello | {stage} | cat") == "HELLO\n"


async def test_two_external_stages_then_builtin(run_pipeline):
    producer = python_stage('import sys; sys.stdout.buffer.write(b"one two\\n" * 10000)')
    consumer = python_stage(
        'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read().replace(b"two", b"three"))'
    )
    assert await run_pipeline(f"{producer} | {consumer} | wc -lw") == "10000 20000\n"


async def test_pipeline_failure_cleans_up_other_stages(run_pipeline, tmp_path):
    baseline = asyncio.all_tasks()
    with pytest.raises(ExecutionError):
        await run_pipeline(f'cat "{(tmp_path / "missing").as_posix()}" | cat | wc')
    remaining = asyncio.all_tasks() - baseline
    assert not [task for task in remaining if not task.done()]


async def test_early_consumer_exit_does_not_block_producer(run_pipeline, tmp_path):
    path = tmp_path / "large.txt"
    path.write_bytes(b"x" * 1000000)
    assert await run_pipeline(f'cat "{path.as_posix()}" | echo done') == "done\n"
