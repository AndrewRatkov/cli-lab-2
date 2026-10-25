import os

from command.command import Command
from utils.exception import ExecutionError


class LsCommand(Command):
    """List directory contents, one entry per line."""

    async def _execute_unsafe(self) -> None:
        """List the supplied directory or the current one, skipping hidden entries."""
        if len(self.args) > 1 or any(arg.startswith("-") and arg != "-" for arg in self.args):
            raise ExecutionError(2)
        path = self.args[0] if self.args else "."
        try:
            if os.path.isdir(path):
                names = sorted(name for name in os.listdir(path) if not name.startswith("."))
            else:
                os.stat(path)
                names = [path]
        except (OSError, ValueError) as error:
            raise ExecutionError(2) from error
        await self._write("".join(name + "\n" for name in names))
