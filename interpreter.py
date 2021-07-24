"""Interpreter for WAM instructions."""

from dataclasses import dataclass, field
from enum import Enum, auto
from model import *
from compiler import ClauseCompiler, PackageCompiler
from typing import Mapping, List, Optional, Iterator

class Cell:
    pass


@dataclass
class Ref(Cell):
    id_: int
    value: Optional[Cell] = None


@dataclass
class AtomCell(Cell):
    value: Atom


@dataclass
class StructCell(Cell):
    name: str
    args: List[Cell]


def to_term(cell: Cell) -> Term:
    return Atom("a")


@dataclass
class InstrAddr:
    functor: Functor
    order: int = 0
    instr: int = 0


class StructArgMode(Enum):
    READ = auto()
    WRITE = auto()


@dataclass
class StructArg:
    mode: StructArgMode
    struct: StructCell
    index: int


@dataclass
class MachineState:
    regs: List[Cell]
    top_ref_id: int
    continuation: Optional[InstrAddr]
    env: Optional["Env"]
    cut_choice: Optional["Choice"]
    struct_arg: Optional[StructArg]


@dataclass
class Env:
    slots: List[Cell]
    continuation: InstrAddr
    cut_choice: Optional["Choice"] = None
    prev: Optional["Env"] = None


@dataclass
class Choice:
    alternative: InstrAddr
    state: MachineState
    trail: List[Ref] = field(default_factory=list)
    prev: Optional["Choice"] = None


Solution = Mapping[Var, Term]


class Machine:
    def __init__(self, package: List[Clause], query: List[Struct]):
        query_name = "query__"
        query_head = Struct(query_name)
        query_clause = Clause(query_head, *query)
        query_compiler = ClauseCompiler(query_clause)
        query_compiler.perms += query_compiler.temps  # All vars in a query should be permanent.
        query_compiler.temps.clear()
        query_code = list(query_compiler.compile())
        query_code.append(Halt())

        self.index = PackageCompiler(*package).compile()
        self.index[query_head.functor()] = [query_code]
        self.instr_ptr = InstrAddr(query_head.functor())
        self.query_vars = query_compiler.perms

        self.choice: Optional[Choice] = None
        self.state = MachineState(
            regs = [],
            top_ref_id = 0,
            continuation = None,
            env = None,
            cut_choice = None,
            struct_arg = None,
        )

    def instr(self) -> Instruction:
        ptr = self.instr_ptr
        predicate = self.index[ptr.functor]
        clause = predicate[ptr.order]
        return clause[ptr.instr]

    def run(self) -> Iterator[Solution]:
        try:
            while self.instr_ptr:
                instr = self.instr()
                if isinstance(instr, Halt):
                    if self.state.env is not None:
                        yield {x: to_term(cell) for x, cell in zip(self.query_vars, self.state.env.slots)}
                    self.backtrack()
                elif isinstance(instr, GetVariable):
                    self.set(instr.addr, self.state.regs[instr.reg.index])
                else:
                    raise NotImplementedError(f"Machine.run: not implemented for instr type {type(instr)}")
        except:
            pass

    def backtrack(self):
        if not self.choice:
            raise NoMoreChoices()
        self.cut_choice = self.choice.machine_state.cut_choice
        self.instr_ptr = self.choice.alternative

    def set(self, addr: Addr, cell: Cell):
        if isinstance(addr, Register):
            self.state.regs[addr.index] = cell
        if isinstance(addr, StackAddr):
            if self.state.env is None:
                raise CompilerError(f"Machine.set: setting permanent variable {addr} without environment")
            self.state.env.slots[addr.index] = cell
        if isinstance(addr, AtomAddr):
            raise CompilerError(f"Trying to write to read-only address {addr} with {cell}")
        raise NotImplementedError(f"Machine.set: not implemented for addr type {type(addr)}")

    def get(self, addr: Addr) -> Cell:
        if isinstance(addr, Register):
            return self.state.regs[addr.index]
        if isinstance(addr, StackAddr):
            if self.state.env is None:
                raise CompilerError(f"Machine.get: getting permanent variable {addr} without environment")
            return self.state.env.slots[addr.index]
        if isinstance(addr, AtomAddr):
            return AtomCell(addr.atom)
        raise NotImplementedError(f"Machine.set: not implemented for addr type {type(addr)}")

    def __str__(self):
        s = ""
        sp, nl = "  ", "\n"
        for functor, preds in self.index.items():
            s += f"{sp*0}{functor}:{nl}"
            for i, pred in enumerate(preds):
                s += f"{sp*1}#{i}:{nl}"
                for instr in pred:
                    s += f"{sp*2}{instr}{nl}"
        return s[:-1]  # Remove last newline


class CompilerError(Exception):
    pass


def main():
    package = [
        # member(E, [H|T]) :- member_(T, E, H).
        # member_(_, E, E).
        # member_([H|T], E, _) :- member_(T, E, H).
        Clause(Struct("member", Var("E"), Struct(".", Var("H"), Var("T"))),
            Struct("member_", Var("T"), Var("E"), Var("H"))),
        Clause(Struct("member_", Var("_"), Var("E"), Var("E"))),
        Clause(Struct("member_", Struct(".", Var("H"), Var("T")), Var("E"), Var("_")),
            Struct("member_", Var("T"), Var("E"), Var("H"))),

        # length([], 0).
        # length([_|T], s(L)) :- length(T, L).  
        Clause(Struct("length", Atom("[]"), Atom("0"))),
        Clause(Struct("length", Struct(".", Var("_"), Var("T")), Struct("s", Var("L"))),
            Struct("length", Var("T"), Var("L"))),
    ]

    # ?- length(L, s(s(s(0)))), member(a, L).
    query = [
        Struct("length", Var("L"), Struct("s", Struct("s", Struct("s", Atom("0"))))),
        Struct("member", Atom("a"), Var("L")),
    ]

    wam = Machine(package, query)
    print(wam)
    for solution in wam.run():
        print(solution)


if __name__ == '__main__':
    main()
