from sage.all import matrix

A = matrix(F, [[F(x)^e for e in unknown] for x in xs])
A.sol<caret>
