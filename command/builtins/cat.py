from enum import Enum

from command.command import Command
from command.options.options_collection import OptionsCollection
from command.options.options_parser import OptionsParser

HIGH_BIT = 0x80
ASCII_SPACE = 0x20
ASCII_DELETE = 0x7F
CARET_OFFSET = ord("@")


class CatOption(Enum):
    """List the supported short flags for the cat command."""

    NUMBER_LINES = "-n"
    NUMBER_NONBLANK = "-b"
    SQUEEZE_BLANK = "-s"
    SHOW_ENDS = "-E"
    SHOW_TABS = "-T"
    SHOW_NONPRINTING = "-v"
    SHOW_ALL = "-A"


class CatFormatter:
    """Format cat output while preserving line state across chunks."""

    def __init__(self, options: OptionsCollection) -> None:
        """Store formatting options and initialize line numbering and blank state."""
        self.options = options
        self.line_number = 1
        self.line_start = True
        self.previous_blank = False

    def format_chunk(self, chunk: str) -> str:
        """Apply the selected formatting options to the next text chunk."""
        if self.options.options_len() == 0:
            return chunk
        return "".join(self._format_character(character) for character in chunk)

    def _format_character(self, character: str) -> str:
        blank = self.line_start and character == "\n"
        if CatOption.SQUEEZE_BLANK in self.options and blank and self.previous_blank:
            return ""
        prefix = self._line_prefix(blank)
        if character == "\n":
            self.previous_blank = blank
            self.line_start = True
            return prefix + (
                "$\n"
                if self.options.has_one_of_options([CatOption.SHOW_ENDS, CatOption.SHOW_ALL])
                else "\n"
            )
        self.line_start = False
        return prefix + self._display(character)

    def _line_prefix(self, blank: bool) -> str:
        if not self.line_start:
            return ""
        if CatOption.NUMBER_NONBLANK in self.options:
            number_line = not blank
        else:
            number_line = CatOption.NUMBER_LINES in self.options
        if not number_line:
            return ""
        prefix = f"{self.line_number:6}\t"
        self.line_number += 1
        return prefix

    def _display(self, character: str) -> str:
        if character == "\t":
            return (
                "^I"
                if self.options.has_one_of_options([CatOption.SHOW_TABS, CatOption.SHOW_ALL])
                else character
            )
        if not self.options.has_one_of_options([CatOption.SHOW_NONPRINTING, CatOption.SHOW_ALL]):
            return character
        return "".join(self._display_byte(byte) for byte in character.encode("utf-8"))

    @staticmethod
    def _display_byte(byte: int) -> str:
        prefix = ""
        if byte >= HIGH_BIT:
            prefix = "M-"
            byte -= HIGH_BIT
        if byte < ASCII_SPACE:
            return prefix + "^" + chr(byte + CARET_OFFSET)
        if byte == ASCII_DELETE:
            return prefix + "^?"
        return prefix + chr(byte)


class CatCommand(Command):
    """Concatenate files or input stream text with optional display formatting."""

    async def _execute_unsafe(self) -> None:
        """Parse cat options and write formatted input to the output stream."""
        parse_result = self._argument_parser.parse(self.args)
        formatter = CatFormatter(parse_result)
        for path in self._input_paths(parse_result.get_operands()):
            async for chunk in self._read_chunks(path):
                await self._write(formatter.format_chunk(chunk))

    def _register_arguments(self) -> OptionsParser:
        parser = OptionsParser()
        parser.register_parameter(CatOption.NUMBER_LINES, CatOption.NUMBER_LINES.value, 0, False)
        parser.register_parameter(
            CatOption.NUMBER_NONBLANK, CatOption.NUMBER_NONBLANK.value, 0, False
        )
        parser.register_parameter(CatOption.SQUEEZE_BLANK, CatOption.SQUEEZE_BLANK.value, 0, False)
        parser.register_parameter(CatOption.SHOW_ENDS, CatOption.SHOW_ENDS.value, 0, False)
        parser.register_parameter(CatOption.SHOW_TABS, CatOption.SHOW_TABS.value, 0, False)
        parser.register_parameter(
            CatOption.SHOW_NONPRINTING, CatOption.SHOW_NONPRINTING.value, 0, False
        )
        parser.register_parameter(CatOption.SHOW_ALL, CatOption.SHOW_ALL.value, 0, False)
        return parser
