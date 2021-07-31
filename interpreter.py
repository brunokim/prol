"""Interpreter for WAM instructions."""

from dataclasses import dataclass, field
from enum import Enum, auto
from model import *
from compiler import ClauseCompiler, PackageCompiler, Code
from typing import Mapping, List, Optional, Iterator, Tuple


class Cell:
    def deref(self):
        return self

    def to_term(self) -> Term:
        raise NotImplementedError("{type(self)}.to_term")

    def __str__(self):
        return f"@{self.to_term()}"
    
    def __repr__(self):
        return str(self)


@dataclass
class Ref(Cell):
    id_: int
    value: Optional[Cell] = None

    def deref(self):
        if self.value is None:
            return self
        return self.value

    def to_term(self) -> Term:
        if self.value is None:
            return Var(f"_{self.id_}")
        return self.value.to_term()
    

@dataclass
class AtomCell(Cell):
    value: Atom

    def to_term(self) -> Term:
        return self.value


@dataclass
class StructCell(Cell):
    name: str
    args: List[Optional[Cell]]

    @property
    def arity(self) -> int:
        return len(self.args)

    def functor(self) -> Functor:
        return Functor(self.name, self.arity)

    @classmethod
    def from_functor(cls, f: Functor) -> "StructCell":
        return StructCell(f.name, [None for _ in range(f.arity)])

    def to_term(self) -> Term:
        args = [
            arg.to_term() if arg is not None else Atom("<nil>")
            for arg in self.args]
        return Struct(self.name, *args)



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
        self.max_iter = 100

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
        iterations = 0
        try:
            while self.instr_ptr and iterations < self.max_iter:
                yield from self.run_instr(self.instr())
                iterations += 1
        except Exception as e:
            import traceback
            traceback.print_tb(e.__traceback__)
            print(e)

    def run_instr(self, instr: Instruction) -> Iterator[Solution]:
        print(instr)
        try:
            if isinstance(instr, Halt):
                if self.state.env is not None:
                    yield {x: to_term(cell) for x, cell in zip(self.query_vars, self.state.env.slots)}
                self.backtrack()
            elif isinstance(instr, Call):
                self.forward()
                self.state.continuation = self.instr_ptr
                self.state.cut_choice = self.choice
                self.instr_ptr = InstrAddr(instr.functor)
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
            elif isinstance(instr, GetValue):
                self.try_unify(self.get_reg(instr.reg), self.get(instr.addr))
            elif isinstance(instr, GetAtom):
                self.read_atom(instr.atom, self.get(instr.reg))
            elif isinstance(instr, GetStruct):
                cell = self.get(instr.reg).deref()
                if isinstance(cell, StructCell):
                    if cell.functor() != instr.functor:
                        raise UnifyError(cell.functor(), instr.functor)
                    self.state.struct_arg = StructArg(StructArgMode.READ, cell)
                elif isinstance(cell, Ref):
                    struct = StructCell.from_functor(instr.functor)
                    self.bind_ref(cell, struct)
                    self.state.struct_arg = StructArg(StructArgMode.WRITE, struct)
                else:
                    raise UnifyError(cell, instr.functor)
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
        except UnifyError as e:
            print(e)
            self.backtrack()

    def forward(self):
        self.instr_ptr.instr += 1

    def backtrack(self):
        # Try next clause in predicate
        predicate = self.index[self.instr_ptr.functor]
        if self.instr_ptr.order < len(predicate)-1:
            self.instr_ptr.order += 1
            self.instr_ptr.instr = 0
            return

        if not self.choice:
            raise NoMoreChoices()
        self.cut_choice = self.choice.machine_state.cut_choice
        self.instr_ptr = self.choice.alternative

    def new_ref(self) -> Ref:
        self.state.top_ref_id += 1
        return Ref(self.state.top_ref_id)

    def set(self, addr: Addr, cell: Cell):
        print(f"{addr} := {cell}")
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

    def unify_arg(self, instr: Instruction) -> InstrAddr:
        struct_arg = self.state.struct_arg

        if struct_arg.mode == StructArgMode.WRITE:
            arg = self.write_arg(instr)
            print(f"{struct_arg.struct.name}[{struct_arg.index}] := {arg}")
            struct_arg.struct.args[struct_arg.index] = arg
            self.forward()
        elif struct_arg.mode == StructArgMode.READ:
            arg = struct_arg.struct.args[struct_arg.index]
            self.read_arg(instr, arg)
        else:
            raise NotImplementedError(f"Machine.unify_arg: not implemented for mode {struct_arg.mode}")

        struct_arg.index += 1
        if struct_arg.index >= struct_arg.struct.arity:
            self.struct_arg = StructArg(StructArgMode.INVALID, None)

    def write_arg(self, instr: Instruction) -> Cell:
        if isinstance(instr, UnifyVariable):
            x = self.new_ref()
            self.set(instr.addr, x)
            return x
        if isinstance(instr, UnifyValue):
            return self.get(instr.addr)
        if isinstance(instr, UnifyAtom):
            return AtomCell(instr.atom)
        raise NotImplementedError(f"Machine.write_arg: not implemented for instruction {instr}")

    def read_arg(self, instr: Instruction, arg: Cell):
        if isinstance(instr, UnifyVariable):
            self.set(instr.addr, arg)
            self.forward()
        elif isinstance(instr, UnifyValue):
            cell = self.get(instr.addr)
            self.try_unify(cell, arg)
        elif isinstance(instr, UnifyAtom):
            self.read_atom(instr.atom, arg)
        else:
            raise NotImplementedError(f"Machine.read_arg: not implemented for instruction {instr}")

    def read_atom(self, atom: Atom, arg: Cell):
        cell = arg.deref()
        if isinstance(cell, AtomCell):
            if cell != atom:
                raise UnifyError(atom, cell)
        elif isinstance(cell, Ref):
            self.bind_ref(cell, atom)
        else:
            raise UnifyError(atom, cell)
        self.forward()

    def try_unify(c1: Cell, c2: Cell):
        stack = [(c1, c2)]
        while stack:
            c1, c2 = stack.pop()
            c1, c2 = c1.deref(), c2.deref()
            if c1 == c2:
                continue
            if isinstance(c1, Ref) or isinstance(c2, Ref):
                if isinstance(c1, Ref) and c1.Value is None:
                    # Always bind older (lower id) to newer (higher id) ref.
                    if not isinstance(c2, Ref) or c2.id_ < c1.id_:
                        ref, value = c1, c2
                    else:
                        ref, value = c2, c1
                elif isinstance(c2, Ref) and c2.Value is None:
                    ref, value = c2, c1
                else:
                    raise CompilerError(f"No unbound refs: {c1}, {c2}")
                self.bind_ref(ref, value)
            elif isinstance(c1, AtomCell):
                if not isinstance(c2, AtomCell) or c1.atom != c2.atom:
                    raise UnifyError(c1, c2)
            elif isinstance(c1, StructCell):
                if not isinstance(c2, StructCell):
                    raise UnifyError(c1, c2)
                f1, f2 = c1.functor(), c2.functor()
                if f1 != f2:
                    raise UnifyError(f1, f2)
                stack.extend(zip(c1.args, c2.args))
            else:
                raise CompilerError(f"Machine.unify: unhandled type {type(c1)}")
        self.forward()

    def bind_ref(self, ref: Ref, value: Cell):
        if ref.value is not None:
            raise CompilerError(f"Machine.bind_ref: ref is bound {ref}")
        ref.value = value
        self.trail(ref)

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


class NoMoreChoices(Exception):
    pass


class CompilerError(Exception):
    pass


class UnifyError(Exception):
    def __init__(self, c1, c2):
        self.c1 = c1
        self.c2 = c2

    def __str__(self):
        return f"{self.c1} != {self.c2}"


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
