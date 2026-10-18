import re
from collections.abc import AsyncIterator
from enum import Enum

from command.command import Command
from command.options.options_collection import OptionsCollection
from command.options.options_parser import OptionsParser
from utils.exception import ExecutionError


class GrepOption(Enum):
    """List the supported matching and context options for grep."""

    WHOLE_WORD = "-w"
    IGNORE_CASE = "-i"
    AFTER_CONTEXT = "-A"


class GrepCommand(Command):
    """Filter files or input stream text by a regular expression."""

    async def _execute_unsafe(self) -> None:
        """Parse grep options and write selected lines to the output stream."""
        options = self._argument_parser.parse(self.args)
        operands = options.get_operands()
        if not operands:
            raise ExecutionError(1)
        pattern, *paths = operands
        after = self._parse_after_context(options)
        expression = self._compile_expression(pattern, options)
        for path in self._input_paths(paths):
            await self._print_matches(path, expression, after)

    @staticmethod
    def _parse_after_context(options: OptionsCollection) -> int:
        context = options.get_option(GrepOption.AFTER_CONTEXT)
        try:
            after = int(context[0]) if context else 0
            if after < 0:
                raise ValueError("Context must be nonnegative")
            return after
        except ValueError as error:
            raise ExecutionError(1) from error

    @staticmethod
    def _compile_expression(pattern: str, options: OptionsCollection) -> re.Pattern[str]:
        flags = re.IGNORECASE if GrepOption.IGNORE_CASE in options else 0
        if GrepOption.WHOLE_WORD in options:
            pattern = rf"(?<!\w)(?:{pattern})(?!\w)"
        try:
            return re.compile(pattern, flags)
        except (ValueError, re.error) as error:
            raise ExecutionError(1) from error

    async def _print_matches(
        self, path: str | None, expression: re.Pattern[str], after: int
    ) -> None:
        remaining = 0
        async for line in self._read_lines(path):
            if expression.search(line.removesuffix("\n")) is not None:
                await self._write(line)
                remaining = after
            elif remaining > 0:
                await self._write(line)
                remaining -= 1

    async def _read_lines(self, path: str | None) -> AsyncIterator[str]:
        fragments = []
        async for chunk in self._read_chunks(path):
            pieces = chunk.split("\n")
            for piece in pieces[:-1]:
                fragments.append(piece)
                yield "".join(fragments) + "\n"
                fragments.clear()
            fragments.append(pieces[-1])
        last_line = "".join(fragments)
        if last_line:
            yield last_line

    def _register_arguments(self) -> OptionsParser:
        parser = OptionsParser()
        parser.register_parameter(GrepOption.WHOLE_WORD, GrepOption.WHOLE_WORD.value, 0, False)
        parser.register_parameter(GrepOption.IGNORE_CASE, GrepOption.IGNORE_CASE.value, 0, False)
        parser.register_parameter(
            GrepOption.AFTER_CONTEXT, GrepOption.AFTER_CONTEXT.value, 1, False
        )
        return parser
