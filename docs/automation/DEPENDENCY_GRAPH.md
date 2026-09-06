# v0.1 dependency graph

```text
#49a -> #49b -> #49c -> #54, #91 -> #57
#53 -> #57, #91
#45 -> #70
#50 (decided 2026-09-06) -> demo/runtime requirement resolution
#92 (decided 2026-09-06) -> #49 lifecycle semantics
```

`#49a` is the recommended next platform-domain slice once today's infra/docs plan lands. It has no implementation dependency and creates the pure lifecycle/Protocol contract needed by the SQLite and recovery slices that follow.
