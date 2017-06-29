#program base.

{a;b;c}.

#program step(k).

{ c(k) }.
q(k) :- c(k).

#program check(k).

 :- not c(5), query(k).


