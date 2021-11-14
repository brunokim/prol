from typing import Optional, Any, List, Iterable
from dataclasses import fields
from enum import Enum, auto


def to_json(obj: Optional[Any], *args):
    if obj is None:
        return None
    if isinstance(obj, list):
        return [to_json(x, *args) for x in obj]
    if hasattr(obj, 'to_json'):
        return obj.to_json(*args)
    return str(obj)


def index(obj: Optional[Any], l: List[Any]) -> Optional[int]:
    if obj is None:
        return None
    return l.index(obj)


class StrJsonMixin:
    def to_json(self):
        return str(self)


class TextCase(Enum):
    SNAKE_CASE = auto()  # a_bunch_of_id_words
    CONST_CASE = auto()  # A_BUNCH_OF_ID_WORDS
    KEBAB_CASE = auto()  # a-bunch-of-id-words
    CAMEL_CASE = auto()  # aBunchOfIdWords
    PASCAL_CASE = auto()  # ABunchOfIdWords


def snake2camel(txt: str) -> str:
    return convert_case(txt, from_style=TextCase.SNAKE_CASE, to_style=TextCase.CAMEL_CASE)


def snake2pascal(txt: str) -> str:
    return convert_case(txt, from_style=TextCase.SNAKE_CASE, to_style=TextCase.PASCAL_CASE)


def convert_case(txt: str, *, from_style: TextCase = None, to_style: TextCase = None) -> str:
    parts = list(from_case(txt, from_style))
    return to_case(parts, to_style)


def from_case(txt: str, case: TextCase) -> Iterable[str]:
    if not txt:
        return []
    if case in (TextCase.SNAKE_CASE, TextCase.CONST_CASE):
        return [part.lower() for part in txt.split('_')]
    if case == TextCase.KEBAB_CASE:
        return [part.lower() for part in txt.split('-')]
    if case in (TextCase.CAMEL_CASE, TextCase.PASCAL_CASE):
        def parts():
            buf = txt[0]
            for ch in txt[1:]:
                if ch.is_upper():
                    yield buf
                    buf = ''
                buf += ch
            yield buf
        return [part.lower() for part in parts()]
    raise ValueError(f"from_case: unhandled case format: {case}")


def to_case(parts: List[str], case: TextCase) -> str:
    if case == TextCase.SNAKE_CASE:
        return '_'.join(part.lower() for part in parts)
    if case == TextCase.CONST_CASE:
        return '_'.join(part.upper() for part in parts)
    if case == TextCase.KEBAB_CASE:
        return '-'.join(part.lower() for part in parts)
    if case == TextCase.CAMEL_CASE:
        first, *rest = parts
        return first.lower() + ''.join(part.title() for part in rest)
    if case == TextCase.PASCAL_CASE:
        return ''.join(part.title() for part in parts)
    raise ValueError(f"to_case: unhandled case format: {case}")
