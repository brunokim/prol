import pytest
from compiler import *


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
              = X2, X1
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
      unify_atom a
      get_struct X1, ./2
       unify_var X0
      unify_atom []
      get_struct X0, h/1
      unify_atom b
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
      unify_atom a
       unify_var X4
               = X0, X1
               > X3, X2
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
      get_atom X3, a
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
       get_atom X1, a
       get_atom X2, b
        get_var X0, X3
       put_atom X0, c
       put_atom X1, d
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
       put_atom X0, a
        get_var X1, X5
       put_atom X1, b
     put_struct X3, g/2
      unify_val X4
      unify_val X5
           call q/4
     """),
    (Clause(Struct('f-eq', Var('X'), Var('Y')),
        Struct('f', Var('X'), Var('A')),
        Struct('f', Var('Y'), Var('B')),
        Struct(r'\==', Var('B'), Struct('p', Atom('a'))),
        Struct('=', Var('A'), Var('B'))),
     r"""
        get_var X1, Y0
        put_var X1, Y1
           call f/2
        put_val X0, Y0
        put_var X1, Y2
           call f/2
     put_struct X0, p/1
     unify_atom a
            \== Y2, X0
              = Y1, Y2
     """),
    (Clause(Struct("query"),
        Struct("length", Var("L"), Struct("s", Struct("s", Struct("s", Atom("0")))))),
     """
        put_var X0, X0
     put_struct X3, s/1
     unify_atom 0
     put_struct X2, s/1
      unify_val X3
     put_struct X1, s/1
      unify_val X2
           call length/2
     """),
]


@pytest.mark.parametrize("clause, instrs", testdata)
def test_compile_clause(clause: Clause, instrs: str):
    compiler = ClauseCompiler(clause)
    got = [str(instr) for instr in compiler.compile()]
    want = [line.strip() for line in instrs.strip().split("\n")]
    assert got == want


def main():
    for clause, _ in testdata:
        print(f'Clause: {clause}')
        cc = ClauseChunks.from_clause(clause)
        print(f'  Permanent vars: {[str(x) for x in cc.perms]}')
        for i, chunk in enumerate(cc.chunks):
            print(f'  Chunk #{i}: {[str(t) for t in chunk.terms]}')
            d = ChunkSets.from_chunk(chunk, cc.temps, i == 0)
            print(f'    Max regs: {d.max_regs}')
            for x in cc.temps:
                use = list(map(str, d.use[x]))
                nouse = list(map(str, d.no_use[x]))
                conflict = list(map(str, d.conflict[x]))
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
