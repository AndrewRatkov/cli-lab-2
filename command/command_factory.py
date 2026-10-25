from typing import ClassVar

from command.builtins import (
    CatCommand,
    CdCommand,
    EchoCommand,
    ExitCommand,
    GrepCommand,
    PwdCommand,
    WcCommand,
)
from command.command import Command
from command.exec_command import ExecCommand
from stream import InStream, OutStream
from utils.session import Session


class CommandFactory:
    """Create built-in commands or fall back to an external program."""

    _commands: ClassVar[dict[str, type[Command]]] = {
        "cat": CatCommand,
        "cd": CdCommand,
        "grep": GrepCommand,
        "echo": EchoCommand,
        "wc": WcCommand,
        "pwd": PwdCommand,
        "exit": ExitCommand,
    }

    def create(
        self, words: list[str], in_stream: InStream, out_stream: OutStream, session: Session
    ) -> Command:
        """Build a command from a nonempty word list and the supplied streams."""
        name, *args = words
        command_type = self._commands.get(name)
        if command_type is None:
            return ExecCommand(words, in_stream, out_stream, session)
        if command_type is CdCommand:
            return CdCommand(args, in_stream, out_stream, session)
        return command_type(args, in_stream, out_stream)
