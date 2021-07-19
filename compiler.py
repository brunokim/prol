from collections import defaultdict, Counter
from model import *
from typing import Sequence, Dict, Iterator, Tuple
from operator import attrgetter


try:
    from pytest import mark
    parametrize = mark.parametrize
except ImportError:
    # On pdb, pytest is not available, so we stub parametrize.
    def parametrize(args, data):
        print("@parametrize stub")
        return lambda f: f


def term_vars(term: Term) -> Iterator[Var]:
    if isinstance(term, Var):
        yield term
    if isinstance(term, Struct):
        for arg in term.args:
            yield from term_vars(arg)


class Chunk:
    def __init__(self, *terms: Struct):
        self.terms = terms

    def vars(self) -> Sequence[Var]:
        xs = {}  # type: Dict[Var, None]
        for term in self.terms:
            xs.update((x, None) for x in term_vars(term))
        return xs.keys()


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
    n = 0

    def count_structs(term: Term):
        nonlocal n
        if isinstance(term, Struct):
            n += 1
            for arg in term.args:
                count_structs(arg)

    for term in chunk.terms:
        for arg in term.args:
            count_structs(arg)
    return n


@dataclass
class ChunkSets:
    max_args: int
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
                if arg in temps:
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

        return ChunkSets(max_args, max_regs, use, no_use, conflict)


class ClauseCompiler:
    def __init__(self, clause: Clause):
        self.clause = clause

        d = ClauseChunks.from_clause(clause)
        self.temps = d.temps
        self.perms = d.perms
        self.chunks = d.chunks

        self.perm_addrs: Optional[Dict[Var, Addr]] = None
        self.temp_addrs: Optional[Dict[Var, Addr]] = None

    def compile(self) -> Iterator[Instruction]:
        self.perm_addrs = {}
        self.temp_addrs = {}
        for i, chunk in enumerate(self.chunks):
            chunk_compiler = ChunkCompiler(chunk, i == 0, self)
            yield from chunk_compiler.compile()
            self.temp_addrs.update(chunk_compiler.temp_addrs)

    def perm_addr(self, x: Var) -> Tuple[StackAddr, bool]:
        if x not in self.perms:
            raise ValueError(f"{x} is not a permanent variable: {self.perms}")
        if x in self.perm_addrs:
            return self.perm_addrs[x], False
        index = len(self.perm_addrs)
        addr = StackAddr(index)
        self.perm_addrs[x] = addr
        return addr, True


class ChunkCompiler:
    def __init__(self, chunk: Chunk, is_head: bool, clause_compiler: ClauseCompiler):
        self.chunk = chunk
        self.is_head = is_head
        self.parent = clause_compiler

        d = ChunkSets.from_chunk(chunk, clause_compiler.temps, is_head)
        self.max_args = d.max_args
        self.max_regs = d.max_regs
        self.use = d.use
        self.no_use = d.no_use
        self.conflict = d.conflict

        self.instructions: Optional[List[Instruction]] = None
        self.delayed_structs: Optional[List[Tuple[Struct, Register]]] = None

        self.free_regs: Optional[Set[Register]] = None
        self.top_reg: Optional[int] = None
        self.temp_addrs: Optional[Dict[Term, Register]] = None
        self.reg_content: Optional[Dict[Register, Term]] = None

    def set_reg(self, reg: Register, term: Term):
        self.temp_addrs[term] = reg
        self.reg_content[reg] = term

    def unset_reg(self, reg: Register, term: Term):
        del self.temp_addrs[term]
        del self.reg_content[reg]

    def compile(self) -> Iterator[Instruction]:
        self.instructions = []
        self.free_regs = {Register(i) for i in range(self.max_regs)}
        self.top_reg = self.max_args

        self.temp_addrs = {}
        self.reg_content = {}

        terms = self.chunk.terms
        if self.is_head:
            head, *terms = terms
            for i in range(head.arity):
                self.free_regs.remove(Register(i))
            self.compile_head(head)

        # TODO: free registers from temp variables that are last referenced
        # in builtins before the last goal.
        for goal in terms[:-1]:
            name = goal.name
            addrs = [self.term_addr(arg) for arg in goal.args]
            self.instructions.append(Builtin([name, *addrs]))

        if terms:
            last_goal = terms[-1]
            for i, arg in enumerate(last_goal.args):
                self.put_term(arg, Register(i), top_level=True)
            self.instructions.append(Call(last_goal.functor()))

        yield from self.instructions

    def compile_head(self, head: Struct):
        self.delayed_structs = []
        for i, arg in enumerate(head.args):
            self.get_term(arg, Register(i))
        while self.delayed_structs:
            delayed = self.delayed_structs.copy()
            self.delayed_structs = []
            for struct, addr in delayed:
                self.get_term(struct, addr)

    def get_term(self, term: Term, reg: Register):
        if isinstance(term, Atom):
            self.instructions.append(GetAtom(reg, term))
            self.free_regs.add(reg)
        elif isinstance(term, Var):
            self.set_reg(reg, term)
            addr, is_new = self.var_addr(term, is_head=True)
            if addr == reg:
                # Filter no-op Get instructions that wouldn't move values around.
                return
            instr = GetVariable(reg, addr) if is_new else GetValue(reg, addr)
            self.instructions.append(instr)
            self.free_regs.add(reg)
        elif isinstance(term, Struct):
            self.instructions.append(GetStruct(reg, term.functor()))
            self.free_regs.add(reg)
            for arg in term.args:
                self.unify_arg(arg)

    def unify_arg(self, term: Term):
        if isinstance(term, Atom):
            self.instructions.append(UnifyAtom(term))
        elif isinstance(term, Var):
            addr, is_new = self.var_addr(term)
            instr = UnifyVariable(addr) if is_new else UnifyValue(addr)
            self.instructions.append(instr)
        elif isinstance(term, Struct):
            addr, _ = self.temp_addr(term)
            self.delayed_structs.append((term, addr))
            self.instructions.append(UnifyVariable(addr))

    def put_term(self, term: Term, reg: Register, *, top_level:bool=False):
        # Move content out of register if in conflict.
        if top_level:
            value = self.reg_content.get(reg)
            if value is not None and value != term and value in self.parent.temps:
                self.unset_reg(reg, value)
                addr, _ = self.temp_addr(value)
                self.instructions.append(GetVariable(reg, addr))

        if isinstance(term, Atom):
            self.instructions.append(PutAtom(reg, term))
        elif isinstance(term, Var):
            addr, is_new = self.var_addr(term)
            if not is_new and addr == reg:
                # Filter no-op PutValue instruction that wouldn't move value around.
                return
            instr = PutVariable(reg, addr) if is_new else PutValue(reg, addr)
            self.instructions.append(instr)
            if isinstance(addr, Register):
                self.free_regs.add(addr)
        elif isinstance(term, Struct):
            self.instructions.append(PutStruct(reg, term.functor()))
            delayed_vars = []  # type: List[Var]
            for arg in term.args:
                if isinstance(arg, Var):
                    delayed_vars.append(arg)
                elif isinstance(arg, Struct):
                    addr = self.term_addr(arg)
                    self.instructions.append(UnifyValue(addr))
                else:
                    self.unify_arg(arg)
            for x in delayed_vars:
                self.unify_arg(x)

    def term_addr(self, term: Term) -> Addr:
        if isinstance(term, Atom):
            return AtomAddr(term)
        if isinstance(term, Var):
            addr, _ = self.var_addr(term)
            return addr
        if isinstance(term, Struct):
            addr, is_new = self.temp_addr(term)
            if is_new:
                self.put_term(term, addr)
            return addr

    def var_addr(self, x: Var, *, is_head:bool=False) -> Tuple[Addr, bool]:
        if x in self.parent.perms:
            return self.parent.perm_addr(x)
        return self.temp_addr(x, is_head=is_head)

    def temp_addr(self, x: Var, *, is_head:bool=False) -> Tuple[Addr, bool]:
        if x in self.temp_addrs:
            return self.temp_addrs[x], False

        use, no_use = self.use[x], self.no_use[x]
        if is_head:
            no_use = no_use | self.conflict[x]

        addr = self.alloc_reg(x, use, no_use)
        self.set_reg(addr, x)
        return addr, True

    def alloc_reg(self, x, use, no_use):
        # Try to allocate a free register.
        free = self.free_regs & use
        if not free:
            free = self.free_regs - no_use
        if free:
            reg = min(free, key=attrgetter('index'))
            self.free_regs.remove(reg)
            return reg

        # Create a new register.
        reg = Register(self.top_reg)
        self.top_reg += 1
        return reg


testdata = [
    (Clause(
        Struct('member', Var('E'), Struct('.', Var('H'), Var('T'))), 
        Struct('member_', Var('T'), Var('E'), Var('H'))),
     """
      get_struct X1, ./2
       unify_var X2
       unify_var X3
         get_var X0, X1
         put_val X0, X3
            call member_/3
     """),
    (Clause(
        Struct('mul', Var('A'), Var('B'), Var('P')),
        Struct('=', Struct('s', Var('B1')), Var('B')),
        Struct('mul', Var('A'), Var('B1'), Var('P1')),
        Struct('add', Var('B1'), Var('P1'), Var('P'))),
     """
        get_var X2, Y0
     put_struct X2, s/1
      unify_var Y1
              = X1, X2
        get_var X1, X3
        put_val X1, Y1
        put_var X2, Y2
           call mul/3
        put_val X0, Y1
        put_val X1, Y2
        put_val X2, Y0
           call add/3
     """),
    (Clause(
        Struct('is_even', Struct('s', Struct('s', Var('X')))),
        Struct('is_even', Var('X'))),
     """
     get_struct X0, s/1
      unify_var X0
     get_struct X0, s/1
      unify_var X0
           call is_even/1
     """),
    (Clause(Struct('f',
        Struct('.',
            Struct('g', Atom('a')),
            Struct('.',
                Struct('h', Atom('b')),
                Atom('[]'))))),
     """
      get_struct X0, ./2
       unify_var X0
       unify_var X1
      get_struct X0, g/1
     unify_const a
      get_struct X1, ./2
       unify_var X0
     unify_const []
      get_struct X0, h/1
     unify_const b
     """),
    (Clause(
        Struct('p', Var('X'), Struct('f', Var('X')), Var('Y'), Var('W')),
        Struct('=', Var('X'), Struct('.', Atom('a'), Var('Z'))),
        Struct('>', Var('W'), Var('Y')),
        Struct('q', Var('Z'), Var('Y'), Var('X'))),
     """
      get_struct X1, f/1
       unify_val X0
      put_struct X1, ./2
     unify_const a
       unify_var X4
               = X1, X0
               > X2, X3
         get_var X0, X5
         put_val X0, X4
         put_val X1, X2
         put_val X2, X5
            call q/3
     """),
    (Clause(
        Struct('p', Var('X'), Var('Y'), Var('Z'), Atom('a')),
        Struct('q', Var('Z'), Var('X'), Var('Y'))),
     """
     get_const X3, a
       get_var X0, X3
       put_val X0, X2
       get_var X1, X2
       put_val X1, X3
          call q/3
     """),
    (Clause(
        Struct('p', Var('X'), Atom('a'), Atom('b')),
        Struct('q', Atom('c'), Atom('d'), Struct('f', Var('X')))),
     """
      get_const X1, a
      get_const X2, b
        get_var X0, X3
      put_const X0, c
      put_const X1, d
     put_struct X2, f/1
      unify_val X3
           call q/3
     """),
    (Clause(
        Struct('p', Var('X'), Var('Y'), Struct('f', Var('Z'))),
        Struct('q', Atom('a'), Atom('b'), Var('Z'), Struct('g', Var('X'), Var('Y')))),
     """
     get_struct X2, f/1
      unify_var X2
        get_var X0, X4
      put_const X0, a
        get_var X1, X5
      put_const X1, b
     put_struct X3, g/2
      unify_val X4
      unify_val X5
           call q/4
     """),
]


@parametrize("clause, instrs", testdata)
def test_compile_clause(clause: Clause, instrs: str):
    compiler = ClauseCompiler(clause)
    got = [str(instr) for instr in compiler.compile()]
    want = [line.strip() for line in instrs.strip().split("\n")]
    assert got == want


def main():
    for clause, _ in testdata:
        print(f'Clause: {clause}')
        cc = ClauseChunks.from_clause(clause)
        print(f'  Permanent vars: {cc.perms}')
        for i, chunk in enumerate(cc.chunks):
            print(f'  Chunk #{i}: {[str(t) for t in chunk.terms]}')
            d = ChunkSets.from_chunk(chunk, cc.temps, i == 0)
            print(f'    Max args: {d.max_args}, Max regs: {d.max_regs}')
            for x in cc.temps:
                use, nouse, conflict = list(map(str, d.use[x])), list(map(str, d.no_use[x])), list(map(str, d.conflict[x]))
                print(f'    USE({x}) = {use}, NOUSE({x}) = {nouse}, CONFLICT({x}) = {conflict}')

        print('Instructions:')
        compiler = ClauseCompiler(clause)
        for instr in compiler.compile():
            print(f'  {instr}')

        print('Addresses')
        addrs = compiler.temp_addrs.copy()
        addrs.update(compiler.perm_addrs)
        for x, addr in addrs.items():
            print(f'  {x}: {addr}')


if __name__ == '__main__':
    main()
