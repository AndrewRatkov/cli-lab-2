import os

from command.command import Command
from stream import InStream, OutStream, Pipe
from utils.exception import ExecutionError
from utils.session import Session


class CdCommand(Command):
    """Change the working directory of the interpreter process."""

    def __init__(
        self, args: list[str], in_stream: InStream, out_stream: OutStream, session: Session
    ):
        super().__init__(args, in_stream, out_stream)
        self.session = session

    async def _execute_unsafe(self) -> None:
        """Change to the supplied directory, HOME, or the previous directory."""
        if (
            len(self.args) > 1
            or isinstance(self.in_stream, Pipe)
            or isinstance(self.out_stream, Pipe)
        ):
            raise ExecutionError(1)
        env = os.environ.copy()
        self.session.apply(env)
        previous = bool(self.args and self.args[0] == "-")
        if not self.args or previous:
            variable = "OLDPWD" if previous else "HOME"
            if variable not in env:
                raise ExecutionError(1)
            directory = env[variable]
        else:
            directory = self.args[0]
        try:
            old_directory = os.getcwd()
            os.chdir(directory)
            new_directory = os.getcwd()
        except (OSError, ValueError) as error:
            raise ExecutionError(1) from error
        os.environ["OLDPWD"] = old_directory
        os.environ["PWD"] = new_directory
        if previous:
            await self._write(new_directory + "\n")
