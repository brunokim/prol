"""Interpreter for WAM instructions."""

from dataclasses import dataclass, field
from enum import Enum, auto
from model import *
from compiler import ClauseCompiler, PackageCompiler, Code
from typing import Mapping, List, Optional, Iterator, Tuple


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

    @property
    def arity(self) -> int:
        return len(self.args)

    @classmethod
    def from_functor(cls, f: Functor) -> "StructCell":
        return StructCell(f.name, [None for _ in range(f.arity)])


def to_term(cell: Cell) -> Term:
    return Atom("a")


@dataclass
class InstrAddr:
    functor: Functor
    order: int = 0
    instr: int = 0


class StructArgMode(Enum):
    INVALID = auto()
    READ = auto()
    WRITE = auto()


@dataclass
class StructArg:
    mode: StructArgMode
    struct: Optional[StructCell] = None
    index: int = 0


@dataclass
class MachineState:
    regs: List[Optional[Cell]]
    top_ref_id: int
    struct_arg: StructArg
    continuation: Optional[InstrAddr]
    env: Optional["Env"]
    cut_choice: Optional["Choice"]


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


def compile_query(query: List[Struct]) -> Tuple[Code, List[Var]]:
    head = Struct("query__")
    clause = Clause(head, *query)
    compiler = ClauseCompiler(clause)
    compiler.perms.extend(compiler.temps)  # All vars in a query should be permanent.
    compiler.temps.clear()
    instrs = list(compiler.compile())
    instrs.append(Halt())
    return Code(head.functor(), instrs), compiler.perms


class Machine:
    def __init__(self, package: List[Clause], query: List[Struct]):
        self.index = PackageCompiler(*package).compile()
        query_code, query_vars = compile_query(query)
        self.index[query_code.functor] = [query_code]
        self.instr_ptr = InstrAddr(query_code.functor)
        self.query_vars = query_vars

        num_regs = 0
        for codes in self.index.values():
            for code in codes:
                num_regs = max(num_regs, code.num_regs)

        self.choice: Optional[Choice] = None
        self.state = MachineState(
            regs = [None for _ in range(num_regs)],
            top_ref_id = 0,
            struct_arg = StructArg(StructArgMode.INVALID),
            continuation = None,
            env = None,
            cut_choice = None,
        )

    def instr(self) -> Instruction:
        ptr = self.instr_ptr
        predicate = self.index[ptr.functor]
        code = predicate[ptr.order]
        return code.instructions[ptr.instr]

    def run(self) -> Iterator[Solution]:
#        try:
            while self.instr_ptr:
                instr = self.instr()
                if isinstance(instr, Halt):
                    if self.state.env is not None:
                        yield {x: to_term(cell) for x, cell in zip(self.query_vars, self.state.env.slots)}
                    self.backtrack()
                elif isinstance(instr, Allocate):
                    self.state.env = Env(
                        slots = [None for _ in range(instr.num_perms)],
                        continuation = self.state.continuation,
                        cut_choice = self.state.cut_choice,
                        prev = self.state.env,
                    )
                    self.state.continuation = None
                    self.forward()
                elif isinstance(instr, Deallocate):
                    self.state.continuation = self.state.env.continuation
                    self.state.env = self.state.env.prev
                    self.forward()
                elif isinstance(instr, GetVariable):
                    self.set(instr.addr, self.get_reg(instr.reg))
                    self.forward()
                elif isinstance(instr, PutVariable):
                    x = self.new_ref()
                    self.set_reg(instr.reg, x)
                    self.set(instr.addr, x)
                    self.forward()
                elif isinstance(instr, PutStruct):
                    s = StructCell.from_functor(instr.functor)
                    self.set_reg(instr.reg, s)
                    self.state.struct_arg = StructArg(StructArgMode.WRITE, s)
                    self.forward()
                elif isinstance(instr, (UnifyVariable, UnifyValue, UnifyAtom)):
                    self.unify_arg(instr)
                else:
                    raise NotImplementedError(f"Machine.run: not implemented for instr type {type(instr)}")
#        except Exception as e:
#            print(e)

    def forward(self):
        self.instr_ptr.instr += 1

    def backtrack(self):
        if not self.choice:
            raise NoMoreChoices()
        self.cut_choice = self.choice.machine_state.cut_choice
        self.instr_ptr = self.choice.alternative

    def new_ref(self) -> Ref:
        self.state.top_ref_id += 1
        return Ref(self.state.top_ref_id)

    def set(self, addr: Addr, cell: Cell):
        if isinstance(addr, Register):
            self.set_reg(addr, cell)
        elif isinstance(addr, StackAddr):
            self.set_stack(addr, cell)
        elif isinstance(addr, AtomAddr):
            raise CompilerError(f"Trying to write to read-only address {addr} with {cell}")
        else:
            raise NotImplementedError(f"Machine.set: not implemented for addr type {type(addr)}")

    def get(self, addr: Addr) -> Cell:
        if isinstance(addr, Register):
            return self.get_reg(addr)
        elif isinstance(addr, StackAddr):
            return self.get_stack(addr)
        elif isinstance(addr, AtomAddr):
            return AtomCell(addr.atom)
        else:
            raise NotImplementedError(f"Machine.set: not implemented for addr type {type(addr)}")

    def set_reg(self, reg: Register, cell: Cell):
        self.state.regs[reg.index] = cell

    def get_reg(self, reg: Register) -> Cell:
        value = self.state.regs[reg.index]
        if value is None:
            raise CompilerError(f"Machine.get_reg: reading uninitialized memory at {reg}")
        return value

    def set_stack(self, addr: StackAddr, cell: Cell):
        if self.state.env is None:
            raise CompilerError(f"Machine.set_reg: setting permanent variable {addr} without environment")
        self.state.env.slots[addr.index] = cell

    def get_stack(self, addr: StackAddr) -> Cell:
        if self.state.env is None:
            raise CompilerError(f"Machine.get_stack: getting permanent variable {addr} without environment")
        value = self.state.env.slots[addr.index]
        if value is None:
            raise CompilerError(f"Machine.get_stack: reading uninitialized memory at {addr}")
        return value

    def unify_arg(self, instr: Instruction):
        struct_arg = self.state.struct_arg

        if struct_arg.mode == StructArgMode.WRITE:
            arg = self.write_arg(instr)
            struct_arg.struct.args[struct_arg.index] = arg
        elif struct_arg.mode == StructArgMode.READ:
            arg = struct_arg.struct.args[struct_arg.index]
            self.read_arg(instr, arg)
        else:
            raise NotImplementedError(f"Machine.unify_arg: not implemented for mode {struct_arg.mode}")

        struct_arg.index += 1
        if struct_arg.index >= struct_arg.struct.arity:
            self.struct_arg = StructArg(StructArgMode.INVALID, None)
        self.forward()

    def write_arg(self, instr: Instruction) -> Cell:
        pass

    def read_arg(self, instr: Instruction, arg: Cell):
        pass

    def __str__(self):
        s = ""
        sp, nl = "  ", "\n"
        for functor, preds in self.index.items():
            s += f"{sp*0}{functor}:{nl}"
            for i, pred in enumerate(preds):
                s += f"{sp*1}#{i}:{nl}"
                for instr in pred.instructions:
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
