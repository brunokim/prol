from dataclasses import dataclass, fields
from typing import List, ClassVar, Any, Tuple
import re

__all__ = [
    'Term', 'Var', 'Atom', 'Struct', 'Functor', 'Clause',
    'Addr', 'Register', 'StackAddr', 'AtomAddr',
    'Instruction', 'Builtin',
    'GetInstr', 'GetValue', 'GetVariable', 'GetAtom', 'GetStruct',
    'PutInstr', 'PutValue', 'PutVariable', 'PutAtom', 'PutStruct',
    'UnifyInstr', 'UnifyValue', 'UnifyVariable', 'UnifyAtom',
    'Call', 'Execute', 'Proceed', 'Halt', 'Allocate', 'Deallocate',
    'to_list', 'from_list',
]


def is_var_name(name: str) -> bool:
    return bool(name) and (name[0].isupper() or name[0] == '_')


def atom_needs_escape(name: str) -> bool:
    LEXICAL = "()',"
    SPACE = r" \n\t"
    SYMBOLS = r"\\=[\].:!@#$%&*+{}^~?/<>-"

    if not name:
        return True
    if is_var_name(name):
        return True
    if re.search(f'[{LEXICAL}{SPACE}]', name):
        return True
    if re.match(r'\d.*\D', name):
        return True
    if re.match(f'[{SYMBOLS}].*[^{SYMBOLS}]', name):
        return True
    return False


class Term:
    pass


class Var(Term):
    def __init__(self, name: str):
        if not is_var_name(name):
            raise ValueError(f"Invalid var name: {name}")
        self.name = name

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, Var) and self.name == other.name

    def __repr__(self):
        return f"Var({self.name!r})"


class Atom(Term):
    def __init__(self, name: str):
        self.name = name

    def __str__(self):
        if atom_needs_escape(self.name):
            return "'" + self.name.replace("'", "''") + "'"
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, Atom) and self.name == other.name

    def __repr__(self):
        return f"Atom({self.name!r})"


@dataclass(frozen=True)
class Functor:
    name: str
    arity: int

    def __str__(self):
        return f"{self.name}/{self.arity}"


class Struct(Term):
    def __init__(self, name: str, *args: "Term"):
        if is_var_name(name):
            raise ValueError(f"Invalid struct name: {name}")
        self.name = name
        self.args = args
        self._hash = hash((name, args))

    @property
    def arity(self) -> int:
        return len(self.args)

    def functor(self) -> Functor:
        return Functor(self.name, self.arity)

    def __str__(self):
        args = ", ".join(str(arg) for arg in self.args)
        return f"{self.name}({args})"

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        return isinstance(other, Struct) and self.name == other.name and self.args == other.args

    def __repr__(self):
        if not self.args:
            return f"Struct({self.name!r})"
        args = ", ".join(repr(arg) for arg in self.args)
        return f"Struct({self.name!r}, {args})"


def to_list(terms: List[Term], tail: Term = Atom("[]")) -> Term:
    l = tail
    for term in terms[::-1]:
        l = Struct(".", term, l)
    return l


def from_list(l: Term) -> Tuple[List[Term], Term]:
    terms: List[Term] = []
    while isinstance(l, Struct) and l.functor() == Functor(".", 2):
        head, tail = l.args
        terms.append(head)
        l = tail
    return terms, l


class Clause:
    def __init__(self, head: Struct, *body: Struct):
        self.head = head
        self.body = body

    def __hash__(self):
        return hash((self.head, self.body))

    def __eq__(self, other):
        return isinstance(other, Clause) and self.head == other.head and self.body == other.body

    def __str__(self):
        if not self.body:
            return f"{self.head}."
        body = ",\n  ".join(str(s) for s in self.body)
        return f"{self.head} :-\n  {body}."

    def __repr__(self):
        return str(self)


class Addr:
    pass


@dataclass(frozen=True)
class Register(Addr):
    index: int

    def __str__(self):
        return f"X{self.index}"


@dataclass(frozen=True)
class StackAddr(Addr):
    index: int

    def __str__(self):
        return f"Y{self.index}"


@dataclass(frozen=True)
class AtomAddr(Addr):
    atom: Atom

    def __str__(self):
        return f"@{self.atom}"


@dataclass(frozen=True)
class Instruction:
    name: ClassVar[str]

    def __str__(self):
        args = ", ".join(str(getattr(self, field.name)) for field in fields(self))
        return f"{self.name} {args}"


@dataclass(frozen=True)
class Builtin(Instruction):
    name = "builtin"
    args: List[Any]

    def __str__(self):
        f, *args = self.args
        args = ", ".join(str(arg) for arg in args)
        return f"{f} {args}"


@dataclass(frozen=True)
class GetInstr(Instruction):
    reg: Register


@dataclass(frozen=True)
class GetValue(GetInstr):
    name = "get_val"
    addr: Addr


@dataclass(frozen=True)
class GetVariable(GetInstr):
    name = "get_var"
    addr: Addr


@dataclass(frozen=True)
class GetAtom(GetInstr):
    name = "get_atom"
    atom: Atom


@dataclass(frozen=True)
class GetStruct(GetInstr):
    name = "get_struct"
    functor: Functor


@dataclass(frozen=True)
class PutInstr(Instruction):
    reg: Register


@dataclass(frozen=True)
class PutValue(PutInstr):
    name = "put_val"
    addr: Addr


@dataclass(frozen=True)
class PutVariable(PutInstr):
    name = "put_var"
    addr: Addr


@dataclass(frozen=True)
class PutAtom(PutInstr):
    name = "put_atom"
    atom: Atom


@dataclass(frozen=True)
class PutStruct(PutInstr):
    name = "put_struct"
    functor: Functor


@dataclass(frozen=True)
class UnifyInstr(Instruction):
    pass


@dataclass(frozen=True)
class UnifyValue(UnifyInstr):
    name = "unify_val"
    addr: Addr


@dataclass(frozen=True)
class UnifyVariable(UnifyInstr):
    name = "unify_var"
    addr: Addr


@dataclass(frozen=True)
class UnifyAtom(UnifyInstr):
    name = "unify_atom"
    atom: Atom


@dataclass(frozen=True)
class Call(Instruction):
    name = "call"
    functor: Functor


@dataclass(frozen=True)
class Execute(Instruction):
    name = "execute"
    functor: Functor


@dataclass(frozen=True)
class Proceed(Instruction):
    name = "proceed"


@dataclass(frozen=True)
class Halt(Instruction):
    name = "halt"


@dataclass(frozen=True)
class Allocate(Instruction):
    name = "allocate"
    num_perms: int


@dataclass(frozen=True)
class Deallocate(Instruction):
    name = "deallocate"
