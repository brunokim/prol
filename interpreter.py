"""Interpreter for WAM instructions."""

from dataclasses import dataclass, field
from enum import Enum, auto
from model import *
from compiler import ClauseCompiler, PackageCompiler, Code
from typing import Mapping, List, Optional, Iterator, Tuple, Dict
from copy import copy, deepcopy


class Cell:
    def deref(self):
        return self

    def to_term(self) -> Term:
        raise NotImplementedError("{type(self)}.to_term")

    def __str__(self):
        return f"@{self.to_term()}"

    def __repr__(self):
        return str(self)


def to_term(cell: Optional[Cell]) -> Term:
    if cell is None:
        return Atom("<nil>")
    return cell.to_term()


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
        args = [to_term(arg) for arg in self.args]
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
    instr_ptr: InstrAddr
    regs: List[Optional[Cell]]
    top_ref_id: int
    struct_arg: StructArg
    continuation: Optional[InstrAddr]
    env: Optional["Env"]


@dataclass
class Env:
    slots: List[Optional[Cell]]
    continuation: Optional[InstrAddr]
    prev: Optional["Env"] = None


@dataclass
class Choice:
    state: MachineState
    trail: List[Ref] = field(default_factory=list)
    prev: Optional["Choice"] = None


@dataclass
class Solution(Mapping[Var, Term]):
    d: Dict[Var, Term]

    def __getitem__(self, key):
        return self.d[key]

    def __iter__(self):
        return iter(self.d)

    def __len__(self):
        return len(self.d)

    def __str__(self):
        if not self.d:
            return "true"
        items = ', '.join(f"{x}: {t}" for x, t in self.d.items())
        return f"{{{items}}}"


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
        self.query_vars = query_vars
        self.max_iter = 10000
        self.has_backtracked = False

        num_regs = 0
        for codes in self.index.values():
            for code in codes:
                num_regs = max(num_regs, code.num_regs)

        self.choice: Optional[Choice] = None
        self.state = MachineState(
            instr_ptr=InstrAddr(query_code.functor),
            regs=[None for _ in range(num_regs)],
            top_ref_id=0,
            struct_arg=StructArg(StructArgMode.INVALID),
            continuation=None,
            env=None,
        )

    def instr(self) -> Instruction:
        ptr = self.state.instr_ptr
        predicate = self.index[ptr.functor]
        code = predicate[ptr.order]
        return code.instructions[ptr.instr]

    def envs(self) -> List[Env]:
        env = self.state.env
        envs = []
        while env is not None:
            envs.append(env)
            env = env.prev
        return envs

    def run(self) -> Iterator[Solution]:
        iterations = 0
        try:
            while iterations < self.max_iter:
                # self.debug_state()
                yield from self.run_instr(self.instr())
                iterations += 1
        except NoMoreChoices:
            pass
        except Exception as e:
            import traceback
            traceback.print_tb(e.__traceback__)
            print(e)

    def debug_state(self):
        mark = '*' if self.has_backtracked else ' '
        num_envs = len(self.envs())
        instr = str(self.instr())
        regs = ' '.join(f'{reg!s:<10}' for reg in self.state.regs)
        slots = ' '.join(f'{slot!s:<10}' for slot in self.state.env.slots) if self.state.env else ''
        print(f"{mark}{'  '*num_envs}{instr:<{40-num_envs*2}} {regs} | {slots}")

    def run_instr(self, instr: Instruction) -> Iterator[Solution]:
        try:
            self.has_backtracked = False
            if isinstance(instr, Halt):
                if self.state.env is not None:
                    yield Solution({x: to_term(cell) for x, cell in zip(self.query_vars, self.state.env.slots)})
                self.backtrack()
            elif isinstance(instr, Call):
                self.state.continuation = self.state.instr_ptr
                self.state.continuation.instr += 1
                self.trampoline(instr.functor)
            elif isinstance(instr, Execute):
                self.trampoline(instr.functor)
            elif isinstance(instr, Proceed):
                if self.state.continuation is None:
                    raise CompilerError(f"proceed called without continuation")
                self.state.instr_ptr = self.state.continuation
                self.state.continuation = None
            elif isinstance(instr, Allocate):
                self.state.env = Env(
                    slots=[None for _ in range(instr.num_perms)],
                    continuation=self.state.continuation,
                    prev=self.state.env,
                )
                self.state.continuation = None
                self.forward()
            elif isinstance(instr, Deallocate):
                if self.state.env is None:
                    raise CompilerError(f"deallocate called without environment")
                self.state.continuation = self.state.env.continuation
                self.state.env = self.state.env.prev
                self.forward()
            elif isinstance(instr, GetVariable):
                self.set(instr.addr, self.get_reg(instr.reg))
                self.forward()
            elif isinstance(instr, GetValue):
                self.unify(self.get_reg(instr.reg), self.get(instr.addr))
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
            elif isinstance(instr, PutValue):
                self.set_reg(instr.reg, self.get(instr.addr))
                self.forward()
            elif isinstance(instr, PutAtom):
                self.set_reg(instr.reg, AtomCell(instr.atom))
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
            self.backtrack()
            self.has_backtracked = True

    def forward(self):
        ptr = self.state.instr_ptr
        code = self.index[ptr.functor][ptr.order]
        if ptr.instr == len(code.instructions)-1:
            # End of code, return to continuation
            ptr = self.state.continuation
            self.state.continuation = None
        ptr.instr += 1
        self.state.instr_ptr = ptr

    def backtrack(self):
        if not self.choice:
            raise NoMoreChoices()
        self.unwind_trail()
        ptr = self.choice.state.instr_ptr
        next_ptr = InstrAddr(ptr.functor, ptr.order+1)
        self.state = deepcopy(self.choice.state)
        self.state.instr_ptr = next_ptr
        self.choice.state.instr_ptr.order += 1
        if len(self.index[ptr.functor])-1 == next_ptr.order:
            # Last clause in predicate, pop last choice point for previous one.
            self.choice = self.choice.prev

    def trampoline(self, functor: Functor):
        self.state.instr_ptr = InstrAddr(functor)

        if len(self.index[functor]) > 1:
            # More than one clause for predicate requires pushing a
            # choice point.
            self.choice = Choice(state=deepcopy(self.state), prev=self.choice)

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
        if struct_arg.struct is None:
            raise CompilerError(f"Machine.unify_arg: struct is None")

        arg: Optional[Cell]
        if struct_arg.mode == StructArgMode.WRITE:
            arg = self.write_arg(instr)
            struct_arg.struct.args[struct_arg.index] = arg
            self.forward()
        elif struct_arg.mode == StructArgMode.READ:
            arg = struct_arg.struct.args[struct_arg.index]
            if arg is None:
                raise CompilerError(f"Machine.unify_arg: {struct_arg.struct.name}[#{struct_arg.index}] is Non")
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
            self.unify(cell, arg)
        elif isinstance(instr, UnifyAtom):
            self.read_atom(instr.atom, arg)
        else:
            raise NotImplementedError(f"Machine.read_arg: not implemented for instruction {instr}")

    def read_atom(self, atom: Atom, arg: Cell):
        cell = arg.deref()
        if isinstance(cell, AtomCell):
            if cell.value != atom:
                raise UnifyError(atom, cell.value)
        elif isinstance(cell, Ref):
            self.bind_ref(cell, AtomCell(atom))
        else:
            raise UnifyError(atom, cell)
        self.forward()

    def unify(self, c1: Cell, c2: Cell):
        stack = [(c1, c2)]
        while stack:
            c1, c2 = stack.pop()
            c1, c2 = c1.deref(), c2.deref()
            if c1 == c2:
                continue
            if isinstance(c1, Ref) or isinstance(c2, Ref):
                if isinstance(c1, Ref) and c1.value is None:
                    # Always bind older (lower id) to newer (higher id) ref.
                    if not isinstance(c2, Ref) or c2.id_ < c1.id_:
                        ref, value = c1, c2
                    else:
                        ref, value = c2, c1
                elif isinstance(c2, Ref) and c2.value is None:
                    ref, value = c2, c1
                else:
                    raise CompilerError(f"No unbound refs: {c1}, {c2}")
                self.bind_ref(ref, value)
            elif isinstance(c1, AtomCell):
                if not isinstance(c2, AtomCell) or c1.value != c2.value:
                    raise UnifyError(c1, c2)
            elif isinstance(c1, StructCell):
                if not isinstance(c2, StructCell):
                    raise UnifyError(c1, c2)
                f1, f2 = c1.functor(), c2.functor()
                if f1 != f2:
                    raise UnifyError(f1, f2)
                for a1, a2 in zip(c1.args, c2.args):
                    if a1 is None or a2 is None:
                        raise CompilerError(f"Machine.unify: uninitialized struct")
                    stack.append((a1, a2))
            else:
                raise CompilerError(f"Machine.unify: unhandled type {type(c1)}")
        self.forward()

    def bind_ref(self, ref: Ref, value: Cell):
        if ref.value is not None:
            raise CompilerError(f"Machine.bind_ref: ref is bound {ref}")
        ref.value = value
        self.trail(ref)

    def trail(self, ref: Ref):
        if self.choice is None:
            return
        choice_top_ref_id = self.choice.state.top_ref_id
        if choice_top_ref_id < ref.id_:
            # Unconditional ref: ref is newer than current choice point, so will
            # be recreated if we backtrack; there's no need to add it to the trail.
            return
        self.choice.trail.append(ref)

    def unwind_trail(self):
        if not self.choice:
            return
        for ref in self.choice.trail:
            ref.value = None
        self.choice.trail = []

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
