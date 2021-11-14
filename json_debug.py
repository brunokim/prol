from typing import Optional, Any, List
from dataclasses import fields


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
