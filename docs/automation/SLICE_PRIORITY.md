# Builder slice priority

Selection is revalidated against current `main`, open domain claims, open automation handoffs and the frozen v0.1 scope before every Builder run.

1. Anything that makes a green check lie or permits release on false evidence.
2. Anything on the v0.1 critical path, in dependency order: `#49a -> #49b -> #49c -> {#53, #54} -> #57`.
3. Active security exposure with no downstream dependents.
4. Defects with a concrete reproduction and a named proving test.
5. Everything else by priority, then age.

Tie-break: prefer the slice that unblocks the most other handoffs.

Never start an item whose dependencies are open or `NEEDS_DECISION`.

Prefer a coherent bundle of same-domain P2 fixes over one isolated P2 when the bundle shares setup, qualification and adjacent code.

Rule 1 remains above the product critical path because false qualification corrupts every downstream judgement. Once qualification is trustworthy, dependency leverage outranks unrelated locality.
