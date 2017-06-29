# planner
> An ASP-based planner

## Usage
```bash
$ planner.py [options] [files]
```
Implements Algorithms A, B and C from [J. Rintanen](https://users.ics.aalto.fi/rintanen/jussi/satplan.html). 

Type ``--help`` for help.

## Description
The input consists of subprograms `base`, `check(t)` , and `step(t)`.
This is also the format of the clingo script [incmode-py.lp](https://github.com/potassco/clingo/blob/master/examples/clingo/iclingo/incmode-py.lp).

Let the program `P(n)` consist of subprograms `base`, `check` with `t=0..n`, and `step` with `t=1..n`.
Then the `planner` returns a stable model of the program consisting of `P(n)` and fact `query(n)`, 
for some `n>=0` such that the program is satisfiable.

The `planner`requires that for all `m>n`, `P(n)` with `query(n)` is satisfiable iff `P(m)` with `query(n)` is satisfiable.

## Additional predicates
The `planner` adds external predicates `query(t)` and `skip(t)`, 
which can only be used in the body of the rules.

While searching for a plan of length `n`, 
the `planner` sets to true `query(n)`, and all atoms `skip(t)` for `t>n`.
The rest of the instances of those predicates are set to `false`.


## Solving Options

Option `--query-at-last` sets `query(m)` to true instead of `query(n)`, where `m` is the latest time point that the `planner` has grounded.

Option `--forbid-actions`  forbids actions at time points after current plan length `n`.
This uses predicate `occurs/2`, and is implemented simply adding the following subprogram:
```bash
#program step(t).
:- occurs(A,t), skip(t).
```

Option `--force-actions`  forces at least one action at time points before current plan length `n`.
It is implemented simply adding the following subprogram:
```bash
#program step(t).
:- not occurs(_,t), not skip(t).
```


## Examples
Replace in the Examples [here](https://github.com/potassco/plasp/blob/master/encodings/strips/README.md) `clingo - incmode.lp` by `planner.py -`.



