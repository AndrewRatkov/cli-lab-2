import asyncio
import os
import sys
from unittest.mock import patch

import pytest

from command.builtins import EchoCommand
from command.command_factory import CommandFactory
from command.exec_command import ExecCommand
from tests.helpers import MemoryStream
from utils.exception import ExecutionError, ExitInterrupt


async def test_output_errors_become_execution_errors(session):
    error = OSError("write failed")
    for words in [["cat"], ["cat", "-n"], ["echo", "hello"], ["wc"], ["pwd"]]:
        source, output = (MemoryStream("hello\n"), MemoryStream())
        command = CommandFactory().create(words, source, output, session)
        with (
            patch.object(output, "write", side_effect=error),
            pytest.raises(ExecutionError) as raised,
        ):
            await command.execute()
        assert raised.value.code == 1


async def test_pwd(run_command):
    assert await run_command(["pwd"]) == os.getcwd() + "\n"
    with pytest.raises(ExecutionError) as raised:
        await run_command(["pwd", "unexpected"])
    assert raised.value.code == 1
    with (
        patch("command.builtins.pwd.os.getcwd", side_effect=OSError),
        pytest.raises(ExecutionError),
    ):
        await run_command(["pwd"])


@pytest.fixture
def cd_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.delenv("OLDPWD", raising=False)
    return tmp_path


@pytest.mark.parametrize("relative", [True, False])
async def test_cd_changes_directory(run_command, cd_directory, relative):
    target = cd_directory / "directory with spaces"
    target.mkdir()
    (target / "example.txt").write_bytes(b"hello\n")
    path = target.name if relative else str(target)
    assert await run_command(["cd", path]) == ""
    assert await run_command(["pwd"]) == str(target) + "\n"
    assert await run_command(["cat", "example.txt"]) == "hello\n"
    script = "import os; print(os.getcwd()); print(os.environ['PWD'])"
    assert await run_command([sys.executable, "-c", script]) == (str(target) + "\n") * 2
    assert await run_command(["cd", ".."]) == ""
    assert os.getcwd() == str(cd_directory)


async def test_cd_home(run_command, cd_directory, monkeypatch, session):
    home = cd_directory / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    assert await run_command(["cd"]) == ""
    assert os.getcwd() == str(home)
    session.set("HOME", str(cd_directory))
    assert await run_command(["cd"]) == ""
    assert os.getcwd() == str(cd_directory)


async def test_cd_previous_directory(run_command, cd_directory):
    target = cd_directory / "target"
    target.mkdir()
    await run_command(["cd", str(target)])
    assert os.environ["OLDPWD"] == str(cd_directory)
    assert await run_command(["cd", "-"]) == str(cd_directory) + "\n"
    assert os.getcwd() == str(cd_directory)
    assert await run_command(["cd", "-"]) == str(target) + "\n"
    assert os.getcwd() == str(target)


@pytest.mark.parametrize("args", [[], ["-"], ["missing"], ["file"], ["a", "b"], [""], ["\0"]])
async def test_cd_invalid_arguments(run_command, cd_directory, monkeypatch, args):
    monkeypatch.delenv("HOME", raising=False)
    (cd_directory / "file").write_bytes(b"text")
    with pytest.raises(ExecutionError) as raised:
        await run_command(["cd", *args])
    assert raised.value.code == 1
    assert os.getcwd() == str(cd_directory)
    assert os.environ["PWD"] == str(cd_directory)
    assert "OLDPWD" not in os.environ


async def test_cd_permission_error(run_command, cd_directory):
    with (
        patch("command.builtins.cd.os.chdir", side_effect=PermissionError),
        pytest.raises(ExecutionError) as raised,
    ):
        await run_command(["cd", "."])
    assert raised.value.code == 1
    assert os.getcwd() == str(cd_directory)


async def test_exit(session):
    command = CommandFactory().create(["exit"], MemoryStream(), MemoryStream(), session)
    with pytest.raises(ExitInterrupt):
        await command.execute()


async def test_echo(run_command):
    assert await run_command(["echo"]) == "\n"
    assert await run_command(["echo", "hello world", "", "$name"]) == "hello world  $name\n"


async def test_factory_creates_builtin_without_executing(session):
    output = MemoryStream()
    words = ["echo", "original"]
    command = CommandFactory().create(words, MemoryStream(), output, session)
    assert isinstance(command, EchoCommand)
    assert output.buffer.getvalue() == ""
    await command.execute()
    assert output.buffer.getvalue() == "original\n"


@pytest.mark.parametrize("text", ["", "\n", "one\r\n\ntwo", "no final newline"])
async def test_cat_stdin_preserves_text(run_command, text):
    assert await run_command(["cat"], text) == text


async def test_multiple_files(run_command, tmp_path):
    first, second = (tmp_path / "a.txt", tmp_path / "b.txt")
    first.write_bytes(b"hi\r\n")
    second.write_bytes(b"end")
    assert await run_command(["cat", str(first), str(second)], "unused input") == "hi\r\nend"
    assert (
        await run_command(["wc", str(first), str(second)])
        == f"1 1 4 {first}\n0 1 3 {second}\n1 2 7 total\n"
    )


@pytest.mark.parametrize(
    "text, expected",
    [("", "0 0 0\n"), ("\n", "1 0 1\n"), ("one\ttwo\nlast", "1 3 12\n"), ("word", "0 1 4\n")],
)
async def test_wc_stdin(run_command, text, expected):
    assert await run_command(["wc"], text) == expected


async def test_wc_word_crossing_chunk_boundary(run_command, tmp_path):
    path = tmp_path / "long.txt"
    path.write_bytes(b"a" * 9000 + b" b\n")
    assert await run_command(["wc", str(path)]) == f"1 2 9003 {path}\n"


async def test_missing_file(run_command, tmp_path):
    path = tmp_path / "missing.txt"
    for name in ["cat", "wc"]:
        with pytest.raises(ExecutionError) as raised:
            await run_command([name, str(path)])
        assert raised.value.code == 1


@pytest.mark.parametrize(
    "args, expected",
    [
        (["-n", "hello"], "hello"),
        (["-n"], ""),
        (["-ne", "one\\ntwo"], "one\ntwo"),
        (["-e", "-E", "one\\ntwo"], "one\\ntwo\n"),
        (["-E", "-e", "one\\ntwo"], "one\ntwo\n"),
        (["-eE", "\\t"], "\\t\n"),
        (["hello", "-n"], "hello -n\n"),
        (["-no", "-n"], "-no -n\n"),
        (["--", "-n"], "-- -n\n"),
    ],
)
async def test_echo_option_order_and_text(run_command, args, expected):
    assert await run_command(["echo", *args]) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("a\\cb", "a"),
        ("\\a\\b\\e\\f\\n\\r\\t\\v\\\\", "\x07\x08\x1b\x0c\n\r\t\x0b\\\n"),
        ("\\0101\\x42", "AB\n"),
        ("\\01012\\x414", "A2A4\n"),
        ("\\0777\\0400", "ÿ\x00\n"),
        ("\\08\\xG", "\x008\\xG\n"),
        ("\\x4a\\x4B", "JK\n"),
        ("\\x41\\cignored", "A"),
        ("\\0", "\x00\n"),
        ("\\q\\x", "\\q\\x\n"),
        ("hello\\", "hello\\\n"),
    ],
)
async def test_echo_escapes(run_command, text, expected):
    assert await run_command(["echo", "-e", text]) == expected


async def test_cat_numbering_and_squeeze(run_command):
    text = "a\n\n\nb\n"
    assert await run_command(["cat", "-n"], text) == "     1\ta\n     2\t\n     3\t\n     4\tb\n"
    assert await run_command(["cat", "-bn"], text) == "     1\ta\n\n\n     2\tb\n"
    assert await run_command(["cat", "-sn"], text) == "     1\ta\n     2\t\n     3\tb\n"


async def test_cat_visible_characters(run_command):
    assert await run_command(["cat", "-ET"], "a\t\nlast") == "a^I$\nlast"
    assert await run_command(["cat", "-v"], "\x00\x1b\x7f\t\n") == "^@^[^?\t\n"
    assert await run_command(["cat", "-A"], "\x00\t\r\n") == "^@^I^M$\n"


async def test_cat_visible_utf8_bytes(run_command):
    assert await run_command(["cat", "-v"], "é\x80߿\x1f \x7f") == "M-CM-)M-BM-^@M-_M-?^_ ^?"


async def test_unicode_counts_and_formatting_across_chunk_boundaries(run_command, tmp_path):
    text = "aé中😀é\tz\n"
    path = tmp_path / "unicode.txt"
    path.write_bytes(text.encode("utf-8"))
    for size in [1, 2, 5, 8192]:
        with patch("command.command.CHUNK_SIZE", size):
            assert await run_command(["cat", str(path)]) == text
            assert await run_command(["cat", "-nET", str(path)]) == "     1\taé中😀é^Iz$\n"
            assert await run_command(["wc", "-Lcmwl", str(path)]) == f"1 2 9 16 9 {path}\n"


async def test_echo_invalid_option_group_is_entirely_text(run_command):
    assert await run_command(["echo", "-e", "-Enz", "a\\tb"]) == "-Enz a\tb\n"


async def test_cat_state_across_files_and_chunks(run_command, tmp_path):
    first, second = (tmp_path / "a", tmp_path / "b")
    first.write_bytes(b"a" * 8193)
    second.write_bytes(b"b\n\n\nc")
    assert (
        await run_command(["cat", "-ns", str(first), str(second)])
        == "     1\t" + "a" * 8193 + "b\n     2\t\n     3\tc"
    )
    first.write_bytes(b"a\n\n")
    second.write_bytes(b"\n\nb")
    assert await run_command(["cat", "-s", str(first), str(second)]) == "a\n\nb"


async def test_cat_b_numbers_only_nonblank(run_command):
    assert await run_command(["cat", "-b"], "a\n\nb\n") == "     1\ta\n\n     2\tb\n"


async def test_cat_n_with_line_ends(run_command):
    assert await run_command(["cat", "-nE"], "a\n\n") == "     1\ta$\n     2\t$\n"


async def test_invalid_utf8_file(run_command, tmp_path):
    path = tmp_path / "bad.bin"
    path.write_bytes(b"\xff\xfe\xfa")
    for name in ["cat", "wc"]:
        with pytest.raises(ExecutionError) as raised:
            await run_command([name, str(path)])
        assert raised.value.code == 1


async def test_wc_selected_counts_and_order(run_command):
    text = "a b\n"
    for args, expected in [
        (["-l"], "1\n"),
        (["-w"], "2\n"),
        (["-m"], "4\n"),
        (["-c"], "4\n"),
        (["-cmwl"], "1 2 4 4\n"),
        (["-l", "-w", "-l"], "1 2\n"),
        (["-L"], "3\n"),
    ]:
        assert await run_command(["wc", *args], text) == expected


async def test_wc_display_width(run_command):
    assert await run_command(["wc", "-L"], "a\tb\nhello") == "9\n"
    assert await run_command(["wc", "-L"], "") == "0\n"
    assert await run_command(["wc", "-L"], "abc\rx") == "3\n"


async def test_wc_totals_use_maximum_width(run_command, tmp_path):
    first, second = (tmp_path / "a", tmp_path / "b")
    first.write_bytes(b"abcd\n")
    second.write_bytes(b"xy\n")
    assert (
        await run_command(["wc", "-lL", str(first), str(second)])
        == f"1 4 {first}\n1 2 {second}\n2 4 total\n"
    )


async def test_double_dash_preserves_filename(run_command, tmp_path, monkeypatch):
    (tmp_path / "-n").write_bytes(b"abc\n")
    monkeypatch.chdir(tmp_path)
    assert await run_command(["cat", "--", "-n"]) == "abc\n"
    assert await run_command(["wc", "--", "-n"]) == "1 1 4 -n\n"


@pytest.mark.parametrize("name", ["cat", "wc"])
async def test_invalid_options(run_command, name):
    with pytest.raises(ExecutionError) as raised:
        await run_command([name, "-z"])
    assert raised.value.code == 1


def test_factory_selects_external_command(session):
    command = CommandFactory().create(["external-program"], MemoryStream(), MemoryStream(), session)
    assert isinstance(command, ExecCommand)


async def test_external_arguments(run_command, tmp_path):
    script = (
        "import sys; from pathlib import Path; "
        "Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')"
    )
    path = tmp_path / "output.txt"
    await run_command([sys.executable, "-c", script, str(path), "a b; $name"])
    assert path.read_text(encoding="utf-8") == "a b; $name"


async def test_external_nonzero_exit(session):
    output = MemoryStream()
    command = ExecCommand(
        [sys.executable, "-c", "print('before failure', flush=True); raise SystemExit(3)"],
        MemoryStream(),
        output,
        session,
    )
    with pytest.raises(ExecutionError) as raised:
        await asyncio.wait_for(command.execute(), 10)
    assert raised.value.code == 3
    assert output.buffer.getvalue().splitlines() == ["before failure"]


async def test_external_missing_program(run_command, tmp_path):
    with pytest.raises(ExecutionError) as raised:
        await run_command([str(tmp_path / "missing-program")])
    assert raised.value.code == 127


async def test_external_launch_permission_error(run_command):
    with (
        patch("command.exec_command.asyncio.create_subprocess_exec", side_effect=PermissionError),
        pytest.raises(ExecutionError) as raised,
    ):
        await run_command(["external-program"])
    assert raised.value.code == 126


async def test_external_streams_and_eof(run_command):
    script = "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"
    for text in ["", "hello\r\n\né中🌍"]:
        output = await run_command([sys.executable, "-c", script], text)
        assert output == text


async def test_external_reads_and_writes_concurrently(run_command):
    script = (
        "import sys; sys.stdout.buffer.write(b'x' * 200000); sys.stdout.buffer.flush(); "
        "sys.stdout.buffer.write(sys.stdin.buffer.read())"
    )
    text = "y" * 200000
    output = await run_command([sys.executable, "-c", script], text)
    assert output == "x" * 200000 + text


async def test_external_unicode_across_read_boundaries(run_command):
    script = "import sys; sys.stdout.buffer.write('Привет 🌍'.encode('utf-8'))"
    with patch("command.exec_command.CHUNK_SIZE", 1):
        assert await run_command([sys.executable, "-c", script]) == "Привет 🌍"


async def test_external_exit_cancels_pending_input(session):
    source, output = (MemoryStream(), MemoryStream())
    cancelled = asyncio.Event()

    async def read_forever():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    command = ExecCommand([sys.executable, "-c", "pass"], source, output, session)
    with patch.object(source, "read_line", side_effect=read_forever):
        await asyncio.wait_for(command.execute(), 10)
    assert cancelled.is_set()


async def test_external_receives_session_environment(session, monkeypatch):
    monkeypatch.setenv("HW1_EXEC_TEST", "parent value")
    session.set("HW1_EXEC_TEST", "local value")
    output = MemoryStream()
    command = ExecCommand(
        [sys.executable, "-c", "import os; print(os.environ['HW1_EXEC_TEST'])"],
        MemoryStream(),
        output,
        session,
    )
    await command.execute()
    assert output.buffer.getvalue().splitlines() == ["local value"]
    assert os.environ["HW1_EXEC_TEST"] == "parent value"


async def test_external_stderr_is_not_forwarded_to_stdout(run_command, capfd):
    script = "import sys; print('output'); print('diagnostic', file=sys.stderr)"
    output = await run_command([sys.executable, "-c", script])
    assert output.splitlines() == ["output"]
    assert capfd.readouterr().err.splitlines() == ["diagnostic"]


async def test_external_cancellation_reaps_process(session):
    started = asyncio.Event()
    processes = []
    create_process = asyncio.create_subprocess_exec

    async def launch(*args, **kwargs):
        process = await create_process(*args, **kwargs)
        processes.append(process)
        return process

    async def read_forever():
        started.set()
        await asyncio.Event().wait()

    source = MemoryStream()
    command = ExecCommand(
        [sys.executable, "-c", "import time; time.sleep(60)"], source, MemoryStream(), session
    )
    with (
        patch("command.exec_command.asyncio.create_subprocess_exec", side_effect=launch),
        patch.object(source, "read_line", side_effect=read_forever),
    ):
        task = asyncio.create_task(command.execute())
        try:
            await asyncio.wait_for(started.wait(), 10)
        finally:
            task.cancel()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 10)
    assert task.cancelled()
    assert processes[0].returncode is not None


async def test_external_stream_failures_reap_process(session):
    cases = [
        ("read_line", OSError("input failed"), ExecutionError),
        ("write", OSError("output failed"), ExecutionError),
        ("write", ValueError("unexpected failure"), ValueError),
    ]
    create_process = asyncio.create_subprocess_exec
    processes = []

    async def launch(*args, **kwargs):
        process = await create_process(*args, **kwargs)
        processes.append(process)
        return process

    for method, error, expected in cases:
        processes.clear()
        source, output = (MemoryStream(), MemoryStream())
        script = "import time; print('ready', flush=True); time.sleep(60)"
        command = ExecCommand([sys.executable, "-c", script], source, output, session)
        stream = source if method == "read_line" else output
        with (
            patch("command.exec_command.asyncio.create_subprocess_exec", side_effect=launch),
            patch.object(stream, method, side_effect=error),
            pytest.raises(expected) as raised,
        ):
            await asyncio.wait_for(command.execute(), 10)
        if isinstance(raised.value, ExecutionError):
            assert raised.value.code == 1
        assert processes[0].returncode is not None


@pytest.mark.parametrize("data", [b"\xff", b"\xd0"])
async def test_external_invalid_utf8_becomes_execution_error(run_command, data):
    script = f"import sys; sys.stdout.buffer.write({data!r})"
    with pytest.raises(ExecutionError) as raised:
        await run_command([sys.executable, "-c", script])
    assert raised.value.code == 1
    assert isinstance(raised.value.__cause__, UnicodeDecodeError)


async def test_external_closes_stdin_early(run_command):
    script = (
        "import os, sys; os.close(0); sys.stdout.buffer.write(b'done'); sys.stdout.buffer.flush()"
    )
    output = await run_command([sys.executable, "-c", script], "x" * 2000000)
    assert output == "done"


@pytest.mark.parametrize(
    "args, expected",
    [
        (["Минимальный"], "Минимальный синтаксис grep\n"),
        (["Минимальный$"], ""),
        (["^Минимальный"], "Минимальный синтаксис grep\n"),
        (["-i", "минимальный"], "Минимальный синтаксис grep\n"),
        (["-w", "Минимал"], ""),
        (["-A", "1", "II"], "II. Примеры\nСледующая строка\n"),  # noqa: RUF001
    ],
)
async def test_grep_file_examples(run_command, tmp_path, args, expected):
    path = tmp_path / "test_grep.txt"
    path.write_bytes(
        "Минимальный синтаксис grep\nI. Введение\nII. Примеры\nСледующая строка\nКонец\n".encode()  # noqa: RUF001
    )
    assert await run_command(["grep", *args, str(path)]) == expected


@pytest.mark.parametrize(
    "args, text, expected",
    [
        (["a[0-9]+$"], "a12\naX\nza3\n", "a12\nza3\n"),
        (["-w", "кот"], "кот\nкотик\n_кот\nкот2\n(кот)\néкот\n", "кот\n(кот)\n"),  # noqa: RUF001
        (["-wi", "кот"], "КОТ!\nкотик\n", "КОТ!\n"),  # noqa: RUF001
        (["-w", "@"], "@\na@\n@b\n(@)\n", "@\n(@)\n"),
        (["-w", "a|ab"], "ab\n", "ab\n"),
        (["-w", "a.*"], "a b!c\n", "a b!c\n"),
        (["-A", "0", "hit"], "hit\nother\n", "hit\n"),
        (["-A", "2", "hit"], "hit\na\nhit\nb\nc\nd\n", "hit\na\nhit\nb\nc\n"),
        (["-A1", "hit"], "hit\nhit\na\nb\n", "hit\nhit\na\n"),
        (["-A", "10", "hit"], "skip\nhit\nlast", "hit\nlast"),
        (["-A", "1", "hit"], "hit\na\nskip\nhit\nb\n", "hit\na\nhit\nb\n"),
        (["^$"], "a\n\nb\n", "\n"),
        ([""], "a\n\nlast", "a\n\nlast"),
        ([""], "", ""),
        (["last$"], "first\nlast", "last"),
        (["--", "-i"], "-i\nother\n", "-i\n"),
    ],
)
async def test_grep_matching_and_context(run_command, args, text, expected):
    assert await run_command(["grep", *args], text) == expected


@pytest.mark.parametrize("size", [1, 2, 5, 8192])
async def test_grep_file_chunk_boundaries(run_command, tmp_path, size):
    path = tmp_path / "input.txt"
    line = "я" * 9000 + " match\n"
    path.write_bytes(("skip\n" + line + "context\nlast").encode("utf-8"))
    with patch("command.command.CHUNK_SIZE", size):
        assert await run_command(["grep", "-A", "1", "match$", str(path)]) == line + "context\n"


async def test_grep_context_resets_between_files(run_command, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.write_bytes(b"hit\n")
    second.write_bytes(b"skip\nhit\nlast\n")
    assert await run_command(["grep", "-A", "2", "hit", str(first), str(second)]) == (
        "hit\nhit\nlast\n"
    )


@pytest.mark.parametrize("args", [[], ["["], ["-A"], ["-A", "x", "a"], ["-A", "-1", "a"]])
async def test_grep_invalid_arguments(run_command, args):
    with pytest.raises(ExecutionError) as raised:
        await run_command(["grep", *args])
    assert raised.value.code == 1


@pytest.mark.parametrize("data", [None, b"\xff"])
async def test_grep_file_errors(run_command, tmp_path, data):
    path = tmp_path / "input.txt"
    if data is not None:
        path.write_bytes(data)
    with pytest.raises(ExecutionError) as raised:
        await run_command(["grep", "a", str(path)])
    assert raised.value.code == 1
