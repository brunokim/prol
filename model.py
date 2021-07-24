from dataclasses import dataclass, fields
from typing import List, ClassVar, Any


def is_var_name(name: str) -> bool:
    return bool(name) and (name[0].isupper() or name[0] == '_')


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


class Atom(Term):
    def __init__(self, name: str):
        if is_var_name(name):
            raise ValueError(f"Invalid atom name: {name}")
        self.name = name

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, Atom) and self.name == other.name


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

    @property
    def arity(self) -> int:
        return len(self.args)

    def functor(self) -> Functor:
        return Functor(self.name, self.arity)

    def __str__(self):
        args = ", ".join(str(arg) for arg in self.args)
        return f"{self.name}({args})"

    def __hash__(self):
        return hash((self.name, self.args))

    def __eq__(self, other):
        return isinstance(other, Struct) and self.name == other.name and self.args == other.args


class Clause:
    def __init__(self, head: Struct, *body: Struct):
        self.head = head
        self.body = body

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


@dataclass
class Instruction:
    name: ClassVar[str]

    def __str__(self):
        args = ", ".join(str(getattr(self, field.name)) for field in fields(self))
        return f"{self.name} {args}"


@dataclass
class Builtin(Instruction):
    args: List[Any]

    def __str__(self):
        f, *args = self.args
        args = ", ".join(str(arg) for arg in args)
        return f"{f} {args}"


@dataclass
class GetInstr(Instruction):
    reg: Register


@dataclass
class GetValue(GetInstr):
    name = "get_val"
    addr: Addr


@dataclass
class GetVariable(GetInstr):
    name = "get_var"
    addr: Addr


@dataclass
class GetAtom(GetInstr):
    name = "get_atom"
    atom: Atom


@dataclass
class GetStruct(GetInstr):
    name = "get_struct"
    functor: Functor


@dataclass
class PutInstr(Instruction):
    reg: Register


@dataclass
class PutValue(PutInstr):
    name = "put_val"
    addr: Addr


@dataclass
class PutVariable(PutInstr):
    name = "put_var"
    addr: Addr


@dataclass
class PutAtom(PutInstr):
    name = "put_atom"
    atom: Atom


@dataclass
class PutStruct(PutInstr):
    name = "put_struct"
    functor: Functor


@dataclass
class UnifyInstr(Instruction):
    pass


@dataclass
class UnifyValue(UnifyInstr):
    name = "unify_val"
    addr: Addr


@dataclass
class UnifyVariable(UnifyInstr):
    name = "unify_var"
    addr: Addr


@dataclass
class UnifyAtom(UnifyInstr):
    name = "unify_atom"
    atom: Atom


@dataclass
class Call(Instruction):
    name = "call"
    functor: Functor

@dataclass
class Halt(Instruction):
    name = "halt"
