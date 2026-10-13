from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import aiofiles

from command.options.options_parser import OptionsParser
from stream import InStream, OutStream
from utils.exception import ExecutionError

CHUNK_SIZE = 8192


class Command(ABC):
    """Define the command interface and shared stream and file helpers."""

    def __init__(self, args: list[str], in_stream: InStream, out_stream: OutStream):
        """Copy command arguments and store the input and output streams."""
        self.args = args.copy()
        self.in_stream = in_stream
        self.out_stream = out_stream
        self._argument_parser = self._register_arguments()

    async def _read_chunks(self, path: str | None = None) -> AsyncIterator[str]:
        try:
            if path is None:
                line = await self.in_stream.read_line()
                while line:
                    yield line
                    line = await self.in_stream.read_line()
            else:
                async with aiofiles.open(path, encoding="utf-8", newline="") as source:
                    chunk = await source.read(CHUNK_SIZE)
                    while chunk:
                        yield chunk
                        chunk = await source.read(CHUNK_SIZE)
        except (OSError, UnicodeError) as error:
            raise ExecutionError(1) from error

    @staticmethod
    def _input_paths(operands: list[str]) -> list[str | None]:
        return list(operands) if operands else [None]

    async def _write(self, text: str) -> None:
        try:
            await self.out_stream.write(text)
        except (OSError, UnicodeError) as error:
            raise ExecutionError(1) from error

    @abstractmethod
    async def _execute_unsafe(self) -> None:
        """Only logic for execution"""
        pass

    async def execute(self) -> None:
        """Run the command, raising ExecutionError on an execution failure
        and managing all given resources"""
        try:
            await self._execute_unsafe()
        except Exception:
            raise
        finally:
            await self.in_stream.close_from_reader()
            await self.out_stream.close_from_writer()

    def _register_arguments(self) -> OptionsParser:
        return OptionsParser()
