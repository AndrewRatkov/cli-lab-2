import argparse
from enum import Enum
from typing import Any

from command.options.options_collection import OptionsCollection
from utils.exception import ExecutionError

DOUBLE_DASH_SYMBOL = "--"


class OptionsParser:
    """Parsing flags for commands"""

    def __init__(self):
        self._parser = argparse.ArgumentParser(exit_on_error=False)
        self._enum_mapping = {}

    def register_parameter(
        self, enum_name: Enum, name: str, nargs: int | str, required: bool
    ) -> None:
        """Registering flag to be parsed and its correlation to in-code enum"""
        if str(nargs) == "0":
            self._parser.add_argument(name, required=required, action="store_const", const="")
        else:
            self._parser.add_argument(name, nargs=nargs, required=required)
        self._enum_mapping[name.strip("-")] = enum_name

    def parse(self, args: list[str]) -> OptionsCollection:
        """Parsing string to options and operands"""
        try:
            raw_options, raw_operands = self._parser.parse_known_args(args)
            options = {}
            for k, v in vars(raw_options).items():
                if v is not None:
                    options[self._enum_mapping[k]] = self._wrap(v)
            operands = list(filter(lambda x: x != DOUBLE_DASH_SYMBOL, raw_operands))
            return OptionsCollection(options, operands)
        except Exception as e:
            raise ExecutionError(1) from e

    def _wrap(self, v: Any) -> list[Any]:
        if isinstance(v, list):
            return v
        return [v]
