"""Compiler for Warren Abstract Machine.

We don't implement all WAM instructions, specially those related to unsafe/local divide of memory.
All memory cells are Python objects, so we don't need to worry about a stack cell pointing to a heap
cell.

We use Debray's algorithm to allocate registers, explained in

Register allocation in a Prolog Machine
Saumya K. Debray
Symposium of Logic Programming, 1986
"""

from collections import defaultdict
from enum import Enum, auto
from model import *
from typing import cast, Sequence, Dict, Iterator, Tuple, Set, List, Union, MutableMapping, Optional, Mapping, Iterable
from operator import attrgetter
from dataclasses import dataclass, field
import itertools as it


@dataclass
class Code:
    functor: Functor
    instructions: List[Instruction]
    num_regs: int = field(init=False)

    def __post_init__(self):
        regs, perms = set(), set()
        for instr in self.instructions:
            # Try to read register from .reg field
            try:
                regs.add(instr.reg)  # pytype: disable=attribute-error
            except AttributeError:
                pass

            # Try to read address from .addr field
            try:
                addr = instr.addr  # pytype: disable=attribute-error
                if isinstance(addr, Register):
                    regs.add(addr)
                if isinstance(addr, StackAddr):
                    perms.add(addr)
            except AttributeError:
                pass

        reg_indices = [reg.index for reg in regs] or [-1]
        self.num_regs = max(reg_indices) + 1

        # Check locations of 'call' instructions
        has_last_call = False
        has_non_last_call = False
        for i, instr in enumerate(self.instructions):
            if not isinstance(instr, Call):
                continue
            if i < len(self.instructions)-1:
                has_non_last_call = True
            else:
                has_last_call = True

        if has_last_call:
            # Replace Call instruction in final position with Execute to save on an
            # environment.
            call = self.instructions.pop()
            self.instructions.append(Execute(call.functor))
        else:
            # Facts and bodies that don't end with 'call' need a 'proceed' instruction
            # to trampoline into continuation.
            self.instructions.append(Proceed())

        # Clauses with permanent variables or non-last calls need an environment.
        if perms or has_non_last_call:
            self.instructions.insert(0, Allocate(len(perms)))

            # Deallocate environment before continuing to next clause.
            last_instr = self.instructions.pop()
            self.instructions.append(Deallocate())
            self.instructions.append(last_instr)


@dataclass
class Index:
    is_var: bool
    by_var: List[Code]
    by_atom: Mapping[Atom, List[Code]]
    by_struct: Mapping[Functor, List[Code]]


def compile_code(functor: Functor, clause: Clause) -> Code:
    instructions = list(ClauseCompiler(clause).compile())
    return Code(functor, instructions)


def index_clauses(clauses: Iterable[Clause]) -> MutableMapping[Functor, List[Index]]:
    by_functor = defaultdict(list)
    for clause in clauses:
        functor = clause.head.functor()
        by_functor[functor].append(clause)

    indices: Dict[Functor, List[Index]] = defaultdict(list)
    for functor, clauses in by_functor.items():
        if not functor.arity:
            # 0-arity functions can't be indexed.
            codes = [compile_code(functor, clause) for clause in clauses]
            indices[functor] = [Index(True, codes, {}, {})]
            continue

        def is_first_arg_var(clause):
            return isinstance(clause.head.args[0], Var)
        for is_var, clauses in it.groupby(clauses, key=is_first_arg_var):
            by_var: List[Code] = []
            by_atom: Dict[Atom, List[Code]] = defaultdict(list)
            by_struct: Dict[Functor, List[Code]] = defaultdict(list)
            for clause in clauses:
                code = compile_code(functor, clause)
                by_var.append(code)

                first_arg = clause.head.args[0]
                if isinstance(first_arg, Atom):
                    by_atom[first_arg].append(code)
                elif isinstance(first_arg, Struct):
                    by_struct[first_arg.functor()].append(code)
            indices[functor].append(Index(is_var, by_var, by_atom, by_struct))

    return indices


class PackageCompiler:
    def __init__(self, *clauses: Clause):
        self.clauses = clauses

    def compile(self) -> MutableMapping[Functor, List[Index]]:
        return index_clauses(self.clauses)


def term_vars(term: Term) -> Iterator[Var]:
    """Yield all vars within term, in depth-first order and with repetition."""
    terms = [term]
    while terms:
        term = terms.pop(0)
        if isinstance(term, Var):
            yield term
        if isinstance(term, Struct):
            terms = list(term.args) + terms


class Chunk:
    """Section of clause containing builtin predicates followed by a non-builtin."""

    def __init__(self, *terms: Struct):
        self.terms = terms

    def vars(self) -> Sequence[Var]:
        """Returns all vars within chunk in depth-first order, without repetition."""
        xs = {}  # type: Dict[Var, None]
        for term in self.terms:
            xs.update((x, None) for x in term_vars(term))
        return list(xs.keys())


# Functors of builtin predicates.
builtins: Set[Functor] = {
    Functor("!", 0),
    Functor("=", 2),
    Functor("<", 2),
    Functor(">", 2),
    Functor("=<", 2),
    Functor(">=", 2),
    Functor("==", 2),
    Functor(r"\==", 2),
}


def gen_chunks(clause: Clause) -> Iterator[Chunk]:
    """Yield chunks from clause."""
    terms = [clause.head]
    for term in clause.body:
        terms.append(term)
        if term.functor() in builtins:
            continue
        yield Chunk(*terms)
        terms = []
    if terms:
        yield Chunk(*terms)


@dataclass
class ClauseChunks:
    """List of chunks from clause, and associated variable classification between permanent and temporary."""
    temps: List[Var]
    perms: List[Var]
    chunks: List[Chunk]

    @classmethod
    def from_clause(cls, clause: Clause) -> "ClauseChunks":
        chunks = list(gen_chunks(clause))
        chunk_vars = [list(chunk.vars()) for chunk in chunks]

        var_chunk_idxs = defaultdict(set)  # type: Dict[Var, Set[int]]
        for i, xs in enumerate(chunk_vars):
            for x in xs:
                var_chunk_idxs[x].add(i)

        temps, perms = [], []
        for x, chunk_idxs in var_chunk_idxs.items():
            if len(chunk_idxs) == 1:
                temps.append(x)
            else:
                perms.append(x)
        return ClauseChunks(temps, perms, chunks)


def count_nested_structs(chunk: Chunk) -> int:
    """Count structs in chunk goals.

    E.g., the chunk [f(s(X), p(q(a)))] has 3 nested structs: s(X), p(...) and q(a).

    >>> count_nested_structs(Chunk(
    ...     Struct("f",
    ...         Struct("s", Var("X")),
    ...         Struct("p", Struct("q", Atom("a"))))))
    ...
    3
    """
    def count_structs(term: Term) -> int:
        terms = [term]
        n = 0
        while terms:
            term = terms.pop(0)
            if isinstance(term, Struct):
                n += 1
                terms = list(term.args) + terms
        return n

    n = 0
    for term in chunk.terms:
        for arg in term.args:
            n += count_structs(arg)
    return n


@dataclass
class ChunkSets:
    """Analysis of temporary variables' locations to compute best registers to allocate."""
    max_regs: int
    use: Dict[Var, Set[Register]]
    no_use: Dict[Var, Set[Register]]
    conflict: Dict[Var, Set[Register]]

    @classmethod
    def from_chunk(cls, chunk: Chunk, temps: List[Var], is_head: bool):
        first_term = chunk.terms[0]
        last_term = chunk.terms[-1]

        # Maximum number of arguments, either input (head) or output (last chunk)
        input_arity = first_term.arity if is_head else 0
        output_arity = last_term.arity if last_term.functor() not in builtins else 0
        max_args = max(input_arity, output_arity)

        # Maximum number of registers: one per argument, temp variable, and nested struct.
        max_regs = max_args + len(temps) + count_nested_structs(chunk)

        # Calc USE set
        use = defaultdict(set)  # type: Dict[Var, Set[Register]]

        def calc_use(term: Struct):
            for i, arg in enumerate(term.args):
                if isinstance(arg, Var) and arg in temps:
                    use[arg].add(Register(i))

        if is_head:
            calc_use(first_term)
        calc_use(last_term)

        # Calc NOUSE set
        no_use = defaultdict(set)  # type: Dict[Var, Set[Register]]
        for x in temps:
            for i, arg in enumerate(last_term.args):
                reg = Register(i)
                if arg in temps and arg != x and reg not in use[x]:
                    no_use[x].add(reg)

        # Calc CONFLICT set
        conflict = defaultdict(set)  # type: Dict[Var, Set[Register]]
        vars_in_last = set(term_vars(last_term))
        for x in temps:
            if x not in vars_in_last:
                continue
            for i, arg in enumerate(last_term.args):
                if arg != x:
                    conflict[x].add(Register(i))

        return ChunkSets(max_regs, use, no_use, conflict)


class AddrAlloc(Enum):
    """Address allocation result."""
    EXISTING = auto()
    NEW_VAR = auto()
    NEW_STRUCT = auto()


class ClauseCompiler:
    """Compiler for a single predicate clause."""

    def __init__(self, clause: Clause):
        self.clause = clause

        d = ClauseChunks.from_clause(clause)
        self.temps = d.temps
        self.perms = d.perms
        self.chunks = d.chunks

        self.perm_addrs: Dict[Var, StackAddr] = {}
        self.temp_addrs: Dict[Term, Register] = {}

    def compile(self) -> Iterator[Instruction]:
        self.perm_addrs = {}
        self.temp_addrs = {}
        for i, chunk in enumerate(self.chunks):
            chunk_compiler = ChunkCompiler(chunk, i == 0, self)
            yield from chunk_compiler.compile()
            self.temp_addrs.update(chunk_compiler.temp_addrs)

    def perm_addr(self, x: Var) -> Tuple[StackAddr, AddrAlloc]:
        if x not in self.perms:
            raise ValueError(f"{x} is not a permanent variable: {self.perms}")
        if x in self.perm_addrs:
            return self.perm_addrs[x], AddrAlloc.EXISTING
        index = len(self.perm_addrs)
        addr = StackAddr(index)
        self.perm_addrs[x] = addr
        return addr, AddrAlloc.NEW_VAR


class ChunkCompiler:
    """Compiler for a clause chunk."""

    def __init__(self, chunk: Chunk, is_head: bool, clause_compiler: ClauseCompiler):
        self.chunk = chunk
        self.is_head = is_head
        self.parent = clause_compiler

        d = ChunkSets.from_chunk(chunk, clause_compiler.temps, is_head)
        self.max_regs = d.max_regs
        self.use = d.use
        self.no_use = d.no_use
        self.conflict = d.conflict

        self.delayed_structs: List[Tuple[Struct, Register]] = []

        self.free_regs: Set[Register] = set()
        self.temp_addrs: Dict[Term, Register] = {}
        self.reg_content: Dict[Register, Term] = {}

    def set_reg(self, reg: Register, term: Term):
        self.temp_addrs[term] = reg
        self.reg_content[reg] = term

    def unset_reg(self, reg: Register, term: Term):
        del self.temp_addrs[term]
        del self.reg_content[reg]

    def compile(self) -> Iterator[Instruction]:
        self.free_regs = {Register(i) for i in range(self.max_regs)}

        self.temp_addrs = {}
        self.reg_content = {}

        terms = self.chunk.terms

        # If this is the clause head, compile first chunk to issue get instructions.
        if self.is_head:
            head, terms = terms[0], terms[1:]
            for i in range(head.arity):
                self.free_regs.remove(Register(i))
            yield from self.compile_head(head)

        # Early return if clause is a fact.
        if not terms:
            return

        last_goal = terms[-1]
        is_last_builtin = (last_goal.functor() in builtins)
        if is_last_builtin:
            builtin_goals = terms
        else:
            builtin_goals = terms[:-1]

        # Compile intermediate, builtin goals.
        # TODO: free registers from temp variables that are last referenced
        # in builtins before the last goal.
        for goal in builtin_goals:
            name = goal.name
            addrs = []
            for arg in goal.args:
                addr, alloc_addr = self.term_addr(arg)
                if alloc_addr == AddrAlloc.NEW_STRUCT:
                    yield from self.put_term(arg, cast(Register, addr))
                addrs.append(addr)
            yield Builtin([name, *addrs])

        # Issue put instructions and predicate call for non-builtin goal.
        if not is_last_builtin:
            for i, arg in enumerate(last_goal.args):
                yield from self.put_term(arg, Register(i), top_level=True)
                self.free_regs.discard(Register(i))
            yield Call(last_goal.functor())

    def compile_head(self, head: Struct) -> Iterator[Instruction]:
        """Compile head of clause.

        Yield get instructions for args, delaying structs after atoms and vars.
        If there is a nested struct, it will be added to the delayed list as well."""
        self.delayed_structs = []
        for i, arg in enumerate(head.args):
            yield from self.get_term(arg, Register(i))
        while self.delayed_structs:
            delayed = self.delayed_structs.copy()
            self.delayed_structs = []
            for struct, addr in delayed:
                yield from self.get_term(struct, addr)

    def get_term(self, term: Term, reg: Register) -> Iterator[Instruction]:
        """Issue get instruction for term."""
        if isinstance(term, Atom):
            yield GetAtom(reg, term)
            self.free_regs.add(reg)
        elif isinstance(term, Var):
            if term not in self.temp_addrs:
                self.set_reg(reg, term)
            addr, alloc_addr = self.var_addr(term, is_head=True)
            if addr == reg:
                # Filter no-op Get instructions that wouldn't move values around.
                return
            instr = GetValue(reg, addr) if alloc_addr == AddrAlloc.EXISTING else GetVariable(reg, addr)
            yield instr
            self.free_regs.add(reg)
        elif isinstance(term, Struct):
            yield GetStruct(reg, term.functor())
            self.free_regs.add(reg)
            for arg in term.args:
                yield from self.unify_arg(arg)
        else:
            raise NotImplementedError(f"get_term: unhandled term type {type(term)}: {term}")

    def unify_arg(self, term: Term) -> Iterator[Instruction]:
        """Issue unify instruction for struct arg."""
        if isinstance(term, Atom):
            yield UnifyAtom(term)
        elif isinstance(term, Var):
            addr, alloc_addr = self.var_addr(term)
            instr = UnifyValue(addr) if alloc_addr == AddrAlloc.EXISTING else UnifyVariable(addr)
            yield instr
        elif isinstance(term, Struct):
            addr, _ = self.temp_addr(term)
            self.delayed_structs.append((term, addr))
            yield UnifyVariable(addr)
        else:
            raise NotImplementedError(f"unify_arg: unhandled term type {type(term)}")

    def put_term(self, term: Term, reg: Register, *, top_level: bool = False) -> Iterator[Instruction]:
        """Issue put instruction for term in register.

        Debray's allocation method lets variables as long as possible in the register.
        If we were to put a term in the same register, we need to move it first
        elsewhere."""

        addr: Addr
        terms = [(term, top_level, reg, True)]
        while terms:
            term, top_level, reg, first_round = terms.pop(0)
            # Conflict resolution: move content out of register if in conflict with an argument.
            if top_level:
                value = self.reg_content.get(reg)
                if value is not None and value != term and (
                        isinstance(value, Var) and value in self.parent.temps or isinstance(value, Struct)):
                    self.unset_reg(reg, value)
                    addr, _ = self.temp_addr(value)
                    if addr != reg:
                        yield GetVariable(reg, addr)

            if isinstance(term, Atom):
                yield PutAtom(reg, term)
            elif isinstance(term, Var):
                addr, alloc_addr = self.var_addr(term)
                if alloc_addr == AddrAlloc.EXISTING:
                    if addr == reg:
                        # Filter no-op PutValue instruction that wouldn't move value around.
                        continue
                    yield PutValue(reg, addr)
                else:
                    yield PutVariable(reg, addr)
                if isinstance(addr, Register):
                    self.free_regs.add(addr)
            elif isinstance(term, Struct):
                if first_round:
                    next_terms = []
                    self.free_regs.discard(reg)  # Reserve reg for put_struct instruction.
                    for arg in term.args:
                        if not isinstance(arg, Struct):
                            continue
                        addr, alloc_addr = self.temp_addr(arg)
                        if alloc_addr == AddrAlloc.NEW_STRUCT:
                            next_terms.append((arg, False, addr, True))
                    next_terms.append((term, top_level, reg, False))
                    terms = next_terms + terms
                else:
                    yield PutStruct(reg, term.functor())
                    for arg in term.args:
                        if isinstance(arg, Struct):
                            yield UnifyValue(self.temp_addrs[arg])
                        else:
                            yield from self.unify_arg(arg)
            else:
                raise NotImplementedError(f"put_term: unhandled term type {type(term)}")

    def term_addr(self, term: Term) -> Tuple[Addr, AddrAlloc]:
        """Return address for a term."""
        if isinstance(term, Atom):
            return AtomAddr(term), AddrAlloc.EXISTING
        if isinstance(term, Var):
            return self.var_addr(term)
        if isinstance(term, Struct):
            return self.temp_addr(term)
        raise NotImplementedError(f"term_addr: unhandled term type {type(term)}")

    def var_addr(self, x: Var, *, is_head: bool = False) -> Tuple[Addr, AddrAlloc]:
        """Return address for a variable."""
        if x in self.parent.perms:
            return self.parent.perm_addr(x)
        return self.temp_addr(x, is_head=is_head)

    def temp_addr(self, x: Union[Var, Struct], *, is_head: bool = False) -> Tuple[Register, AddrAlloc]:
        """Return register for a variable or struct.

        Debray's allocation algorithm seeks to put address in registers used by the variable
        (either in first or last goals of chunk), and avoid registers used by other variables (NOUSE set)
        or any term in the last goal (CONFLICT set)."""
        if x in self.temp_addrs:
            return self.temp_addrs[x], AddrAlloc.EXISTING

        use, no_use = self.use[x], self.no_use[x]
        if not is_head:
            # Conflict avoidance: do not use registers that are necessary for last goal args.
            no_use = no_use | self.conflict[x]

        addr = self.alloc_reg(x, use, no_use)
        self.set_reg(addr, x)

        alloc = AddrAlloc.NEW_VAR if isinstance(x, Var) else AddrAlloc.NEW_STRUCT
        return addr, alloc

    def alloc_reg(self, x: Union[Var, Struct], use: Set[Register], no_use: Set[Register]) -> Register:
        """Allocate a register for a variable or struct."""
        # Try to allocate a free register.
        free = self.free_regs & use
        if not free:
            free = self.free_regs - no_use
        reg = min(free, key=attrgetter('index'))
        self.free_regs.remove(reg)
        return reg
