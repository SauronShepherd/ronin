# v0.1 dependency graph

```text
#99 (49a) -> #100 (49b) -> #101 (49c) -> #54, #91 -> #57
#53 -> #57, #91
#45 -> #70, #72
#50 (decided 2026-09-06) -> demo/runtime requirement resolution
#92 (decided 2026-09-06) -> #99 lifecycle semantics
```

`#99` is the recommended next platform-domain slice once today's infra/docs plan lands. It has no implementation dependency and creates the pure lifecycle/Protocol contract needed by the SQLite and recovery slices that follow.

`#100` and `#101` are deliberately blocked until their predecessor lands. This prevents the Builder from selecting an implementation whose contract is still moving.
