import copy
from enum import Enum


class OptionsCollection:
    """Structure that holds options and operands"""

    def __init__(self, options: dict[Enum, list[str]], operands: list[str]):
        self._options = options.copy()
        self._operands = operands.copy()

    def options_len(self) -> int:
        return len(self._options)

    def __contains__(self, option: Enum) -> bool:
        return option in self._options

    def has_one_of_options(self, options: list[Enum]) -> bool:
        return any(option in self for option in options)

    def get_option(self, option: Enum) -> list[str] | None:
        return self._options.get(option, None)

    def get_operands(self) -> list[str]:
        return self._operands

    def set_default_options(self, options: dict[Enum, list[str]]):
        if not self._options:
            self._options = copy.deepcopy(options)
