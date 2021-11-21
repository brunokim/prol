"""Interpreter for WAM instructions."""

from dataclasses import dataclass, field
from enum import Enum, auto
from model import *
from compiler import ClauseCompiler, PackageCompiler, Code, Index
from functools import total_ordering
from typing import Mapping, List, Optional, Iterator, Tuple, Dict, Any
from enum import Enum, auto
import operator
import json
from json_debug import to_json, index


__all__ = [
    'Cell', 'Ref', 'AtomCell', 'StructCell',
    'Machine', 'Solution', 'Env',
]


class Ordering(Enum):
    LT = auto()
    EQ = auto()
    GT = auto()

    @staticmethod
    def compare(x, y) -> "Ordering":
        if x < y:
            return Ordering.LT
        if x > y:
            return Ordering.GT
        return Ordering.EQ


@total_ordering
class Cell:
    def deref(self):
        return self

    @classmethod
    def order(cls) -> int:
        raise NotImplementedError("{cls}.order")

    def compare(self, other) -> Ordering:
        raise NotImplementedError("{type(self)}.compare")

    def __lt__(self, other: "Cell") -> bool:
        if self.order() < other.order():
            return True
        if self.order() > other.order():
            return False
        return self.compare(other) == Ordering.LT

    def to_json(self):
        return str(to_term(self))


@dataclass
class Ref(Cell):
    id_: int
    value: Optional[Cell] = None

    @classmethod
    def order(cls):
        return 10

    def deref(self):
        if self.value is None:
            return self
        return self.value

    def compare(self, other: "Ref") -> Ordering:
        return Ordering.compare(self.id_, other.id_)


@dataclass
class AtomCell(Cell):
    value: Atom

    @classmethod
    def order(cls):
        return 20

    def compare(self, other: "AtomCell") -> Ordering:
        return Ordering.compare(self.value.name, other.value.name)


@dataclass
class StructCell(Cell):
    name: str
    args: List[Optional[Cell]]

    @classmethod
    def order(cls):
        return 30

    @property
    def arity(self) -> int:
        return len(self.args)

    def functor(self) -> Functor:
        return Functor(self.name, self.arity)

    @classmethod
    def from_functor(cls, f: Functor) -> "StructCell":
        return StructCell(f.name, [None for _ in range(f.arity)])

    def compare(self, other: "StructCell") -> Ordering:
        pairs = [(self.arity, other.arity), (self.name, other.name)]
        pairs += zip(self.args, other.args)
        for t1, t2 in pairs:
            if t1 is None or t2 is None:
                raise CompilerError(f"comparing incomplete struct: {self}, {other}")
            order = Ordering.compare(t1, t2)
            if order != Ordering.EQ:
                return order
        return Ordering.EQ


def to_term(cell: Optional[Cell]) -> Term:
    """Iterative conversion of cells to terms"""
    stack = [cell]
    terms = []

    def gen_terms(elem):
        if elem is None:
            yield Atom("")
        elif isinstance(elem, AtomCell):
            yield elem.value
        elif isinstance(elem, Ref):
            if elem.value is None:
                yield Var(f"_{elem.id_}")
            else:
                stack.append(elem.value)
        elif isinstance(elem, StructCell):
            # Place args reversed so that they are popped in order. The last element to be popped
            # is the functor, which builds a struct from the top elements of terms stack.
            stack.append(elem.functor())
            stack.extend(reversed(elem.args))
        elif isinstance(elem, Functor):
            args = terms[-elem.arity:]
            del terms[-elem.arity:]
            yield Struct(elem.name, *args)
        else:
            raise ValueError(f"unhandled cell type {type(cell)} ({cell})")
    while stack:
        elem = stack.pop()
        terms.extend(gen_terms(elem))
    assert len(terms) == 1, f"expected 1 term when converting cell {cell!r}, got {len(terms)}: {terms}"
    return terms[0]


def indexed_codes(indices: List[Index], first_arg: Optional[Cell]) -> List[Code]:
    codes = []
    cell = first_arg.deref() if first_arg else None
    for index in indices:
        if cell is None or isinstance(cell, Ref) or index.is_var:
            codes.extend(index.by_var)
        elif isinstance(cell, AtomCell):
            codes.extend(index.by_atom[cell.value])
        elif isinstance(cell, StructCell):
            codes.extend(index.by_struct[cell.functor()])
        else:
            raise CompilerError(f"unhandled cell type {type(cell)} ({cell})")
    return codes


@dataclass(frozen=True)
class InstrAddr:
    functor: Functor
    codes: List[Code]
    order: int = 0
    instr: int = 0

    def step(self) -> "InstrAddr":
        code = self.codes[self.order]
        if self.instr >= len(code.instructions)-1:
            # End of code reached
            raise CompilerError(f"reached end-of-function without proceed instruction at {self}")
        return InstrAddr(self.functor, self.codes, self.order, self.instr+1)

    def next_clause(self) -> "InstrAddr":
        if self.order >= len(self.codes)-1:
            raise CompilerError(f"reached last clause in predicate during backtrack at {self}")
        return InstrAddr(self.functor, self.codes, self.order+1, 0)

    def is_last_clause(self) -> bool:
        return len(self.codes)-1 == self.order

    def curr_instr(self) -> "Instruction":
        code = self.codes[self.order]
        return code.instructions[self.instr]

    def to_json(self, codes):
        return {
            'ClausePos': index(self.codes[self.order], codes),
            'Pos': self.instr,
            'Ref': f"pos {self.instr}",
        }


class StructArgMode(Enum):
    INVALID = auto()
    READ = auto()
    WRITE = auto()


@dataclass
class StructArg:
    mode: StructArgMode
    struct: Optional[StructCell] = None
    index: int = 0

    def to_json(self):
        return {
            'Cell': to_json(self.struct),
            'Mode': self.mode.name.lower(),
            'Index': self.index,
        }


@dataclass
class MachineState:
    instr_ptr: InstrAddr
    regs: List[Optional[Cell]]
    top_ref_id: int
    struct_arg: StructArg
    continuation: Optional[InstrAddr]
    env: Optional["Env"]
    depth: int

    def clone(self) -> "MachineState":
        return MachineState(
            self.instr_ptr,
            list(self.regs),
            self.top_ref_id,
            self.struct_arg,
            self.continuation,
            self.env.clone() if self.env else None,
            self.depth,
        )


@dataclass
class Env:
    slots: List[Optional[Cell]]
    continuation: Optional[InstrAddr]
    num_executes: int
    prev: Optional["Env"] = None

    def clone(self) -> "Env":
        return Env(
            list(self.slots),
            self.continuation,
            self.num_executes,
            self.prev.clone() if self.prev else None,
        )

    @staticmethod
    def stack(env: Optional["Env"]) -> List["Env"]:
        envs = []
        while env:
            envs.append(env)
            env = env.prev
        return reversed(envs)

    def to_json(self, codes, envs):
        return {
            'PrevPos': index(self.prev, envs),
            'Continuation': to_json(self.continuation, codes),
            'PermanentVars': to_json(self.slots),
        }


@dataclass
class Choice:
    state: MachineState
    trail: List[Ref] = field(default_factory=list)
    prev: Optional["Choice"] = None

    def to_json(self, codes, choices, envs):
        return {
            'PrevPos': index(self.prev, choices),
            'NextAlternative': to_json(self.state.instr_ptr.next_clause(), codes),
            'Args': to_json(self.state.regs),
            'Trail': to_json(self.trail),
            'Attributes': [],
            'LastRefID': self.state.top_ref_id,
            'EnvPos': index(self.state.env, envs),
            'CutChoicePos': None,
            'Continuation': to_json(self.state.continuation, codes),
        }


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
    def __init__(self, package: List[Clause], query: List[Struct], *, max_iter=float("Inf")):
        query_code, query_vars = compile_query(query)
        self.indices_by_functor = PackageCompiler(*package).compile()
        self.indices_by_functor[query_code.functor] = [Index(True, [query_code], {}, {})]
        self.query_vars = query_vars
        self.iter = 0
        self.max_iter = max_iter
        self.has_backtracked = False
        self.debug_filename = None
        self.debug_codes = None

        # Utility for debugging grammars, storing the deepest solution, which is likely to
        # represent the farthest in the string we got before failing.
        self.store_deepest_solution = False
        self.max_error_depth = 0
        self.deepest_state = None
        self.deepest_solution = None

        num_regs = 0
        for indices in self.indices_by_functor.values():
            for index in indices:
                for code in index.by_var:
                    num_regs = max(num_regs, code.num_regs)

        self.choice: Optional[Choice] = None
        self.state = MachineState(
            instr_ptr=InstrAddr(query_code.functor, [query_code]),
            regs=[None for _ in range(num_regs)],
            top_ref_id=0,
            struct_arg=StructArg(StructArgMode.INVALID),
            continuation=None,
            env=None,
            depth=0,
        )

    def run(self) -> Iterator[Solution]:
        try:
            self.debug_init()
            while self.iter < self.max_iter:
                self.debug_state()
                yield from self.run_instr(self.instr())
                self.iter += 1
            raise MaxIterReached(self.max_iter)
        except NoMoreChoices:
            pass
        except Exception as e:
            import traceback
            traceback.print_tb(e.__traceback__)
            print(e)

    def debug_init(self):
        if not self.debug_filename:
            return
        self.debug_codes = list(indices_codes(self.indices_by_functor))
        with open(self.debug_filename, 'w') as f:
            json.dump(self.to_json(include_clauses=True), f)
            f.write('\n')

    def debug_state(self):
        if not self.debug_filename:
            return
        with open(self.debug_filename, 'a') as f:
            json.dump(self.to_json(), f)
            f.write('\n')

    def solution_for(self, state: MachineState) -> Optional[Solution]:
        if not state.env:
            return None
        first_env = state.env
        while first_env.prev:
            first_env = first_env.prev
        return Solution({x: to_term(cell) for x, cell in zip(self.query_vars, first_env.slots)})

    def run_instr(self, instr: Instruction) -> Iterator[Solution]:
        try:
            self.has_backtracked = False
            instr_fn = getattr(self, f'run_{instr.name}', None)
            if instr_fn is not None:
                instr_fn(instr)
            elif isinstance(instr, Halt):
                if self.state.env is not None:
                    yield self.solution_for(self.state)
                self.backtrack()
            else:
                raise NotImplementedError(f"Machine.run: not implemented for instr type {type(instr)}")
        except UnifyError as e:
            self.backtrack()
            self.has_backtracked = True

    comparisons = {
        '<': operator.lt,
        '>': operator.gt,
        '=<': operator.le,
        '>=': operator.ge,
        '==': operator.eq,
        '\\==': operator.ne,
    }

    def run_builtin(self, instr: Builtin):
        name, *addrs = instr.args
        if name == '=':
            a1, a2 = addrs
            self.unify(self.get(a1), self.get(a2))
        elif name in self.comparisons:
            comparison = self.comparisons[name]
            a1, a2 = addrs
            c1, c2 = self.get(a1).deref(), self.get(a2).deref()
            if comparison(c1, c2):
                self.forward()
            else:
                self.backtrack()
        else:
            raise ValueError(f"Machine.run_builtin: unknown builtin name {name!r}")

    def run_call(self, instr: Call):
        self.state.depth += 1
        self.state.continuation = self.state.instr_ptr.step()
        self.trampoline(instr.functor)

    def run_execute(self, instr: Execute):
        self.state.depth += 1
        self.state.env.num_executes += 1
        self.trampoline(instr.functor)

    def run_proceed(self, instr: Proceed):
        self.state.depth -= self.state.env.num_executes + 1
        self.state.env.num_executes = 0
        if self.state.continuation is None:
            raise CompilerError(f"proceed called without continuation")
        self.state.instr_ptr = self.state.continuation
        self.state.continuation = None

    def run_allocate(self, instr: Allocate):
        self.state.env = Env(
            slots=[None for _ in range(instr.num_perms)],
            continuation=self.state.continuation,
            num_executes=0,
            prev=self.state.env,
        )
        self.state.continuation = None
        self.forward()

    def run_deallocate(self, instr: Deallocate):
        if self.state.env is None:
            raise CompilerError(f"deallocate called without environment")
        self.state.continuation = self.state.env.continuation
        self.state.env = self.state.env.prev
        self.forward()

    def run_get_var(self, instr: GetVariable):
        self.set(instr.addr, self.get_reg(instr.reg))
        self.forward()

    def run_get_val(self, instr: GetValue):
        self.unify(self.get_reg(instr.reg), self.get(instr.addr))

    def run_get_atom(self, instr: GetAtom):
        self.read_atom(instr.atom, self.get(instr.reg))

    def run_get_struct(self, instr: GetStruct):
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

    def run_put_var(self, instr: PutVariable):
        x = self.new_ref()
        self.set_reg(instr.reg, x)
        self.set(instr.addr, x)
        self.forward()

    def run_put_val(self, instr: PutValue):
        self.set_reg(instr.reg, self.get(instr.addr))
        self.forward()

    def run_put_atom(self, instr: PutAtom):
        self.set_reg(instr.reg, AtomCell(instr.atom))
        self.forward()

    def run_put_struct(self, instr: PutStruct):
        s = StructCell.from_functor(instr.functor)
        self.set_reg(instr.reg, s)
        self.state.struct_arg = StructArg(StructArgMode.WRITE, s)
        self.forward()

    def run_unify_var(self, instr: UnifyVariable):
        self.unify_arg(instr)

    def run_unify_val(self, instr: UnifyValue):
        self.unify_arg(instr)

    def run_unify_atom(self, instr: UnifyAtom):
        self.unify_arg(instr)

    def instr(self) -> Instruction:
        return self.state.instr_ptr.curr_instr()

    def forward(self):
        self.state.instr_ptr = self.state.instr_ptr.step()

    def backtrack(self):
        if not self.choice:
            raise NoMoreChoices()
        if self.store_deepest_solution and self.state.depth > self.max_error_depth:
            # Store the machine state in its deepest iteration, where presumably it
            # got closer to a solution.
            # This may help the user discover some error in their program.
            self.deepest_state = self.state.clone()
            self.deepest_solution = self.solution_for(self.state)
            self.max_error_depth = self.state.depth

        self.unwind_trail()
        self.choice.state.instr_ptr = self.choice.state.instr_ptr.next_clause()
        if self.choice.state.instr_ptr.is_last_clause():
            # Last clause in predicate, pop last choice point for previous one.
            self.state = self.choice.state
            self.choice = self.choice.prev
        else:
            self.state = self.choice.state.clone()

    def trampoline(self, functor: Functor):
        first_arg = None
        if self.state.regs:
            first_arg = self.state.regs[0]
        indices = self.indices_by_functor[functor]
        codes = indexed_codes(indices, first_arg)
        if not codes:
            self.backtrack()
            return

        self.state.instr_ptr = InstrAddr(functor, codes)
        if len(codes) > 1:
            # More than one clause for predicate requires pushing a choice point
            self.choice = Choice(state=self.state.clone(), prev=self.choice)

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
        for functor, indices in self.indices_by_functor.items():
            s += f"{sp*0}{functor}:{nl}"
            i = 0
            for index in indices:
                for code in index.by_var:
                    s += f"{sp*1}#{i}:{nl}"
                    for instr in code.instructions:
                        s += f"{sp*2}{instr}{nl}"
                    i += 1
        return s[:-1]  # Remove last newline

    def to_json(self, include_clauses=False):
        choices, envs = self.live_choices_and_envs()
        clauses = to_json(self.debug_codes) if include_clauses else []
        obj = {
            'Mode': 'Run',
            'Clauses': clauses,
            'CodePtr': to_json(self.state.instr_ptr, self.debug_codes),
            'Continuation': to_json(self.state.continuation, self.debug_codes),
            'Reg': to_json(self.state.regs),
            'ComplexArg': to_json(self.state.struct_arg),
            'UnifFrames': [],
            'EnvPos': index(self.state.env, envs),
            'Envs': to_json(envs, self.debug_codes, envs),
            'ChoicePos': index(self.choice, choices),
            'ChoicePoints': to_json(choices, self.debug_codes, choices, envs),
            'LastRefId': self.state.top_ref_id,
            'Backtracked': self.has_backtracked,
            'Attributes': [],
        }
        return obj

    def live_choices_and_envs(self):
        # Collect live choice points
        choice = self.choice
        choices = []
        while choice is not None:
            choices.append(choice)
            choice = choice.prev

        # Collect live environments
        env_leafs = [self.state.env] + [choice.state.env for choice in choices]
        env_leafs = {id(env): env for env in env_leafs if env is not None}
        envs = []
        for id_env, leaf_env in env_leafs.items():
            envs.append(leaf_env)
            env = leaf_env.prev
            while env is not None and id(env) not in env_leafs:
                envs.append(env)
                env = env.prev

        return choices, envs


def indices_codes(indices_by_functor):
    for indices in indices_by_functor.values():
        for index in indices:
            yield from index.by_var


class NoMoreChoices(Exception):
    pass


class MaxIterReached(Exception):
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
    wam.debug_filename = 'debugtest/interpreter.jsonl'
    for solution in wam.run():
        print(solution)


if __name__ == '__main__':
    main()
