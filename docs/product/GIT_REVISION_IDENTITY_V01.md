# Ronin v0.1 Git revision identity

Ronin captures a local Git repository as a commit object ID plus an optional `dirty_patch_sha256`. The dirty digest is canonical execution identity for modified worktrees; raw dirty file contents are not persisted merely to construct that identity.

## Dirty identity input

`ronin/git-dirty-v1` hashes two bounded logical sections:

1. Git's binary tracked diff against `HEAD`.
2. A deterministic sequence of untracked regular-file records ordered by normalized repository-relative path.

Each untracked record contributes:

- repository-relative path encoded with `/` separators;
- normalized Git-style mode (`100644` or `100755`);
- byte length;
- SHA-256 of the file content.

The content digest, not the raw bytes, enters the untracked record. Existing ignored files remain excluded because discovery uses `git ls-files --others --exclude-standard`.

## Executable-mode normalization

On POSIX platforms, Ronin follows Git's regular-file executable distinction: an untracked file with the owner executable bit (`S_IXUSR`) maps to `100755`; otherwise it maps to `100644`. Group/other permission detail is intentionally normalized away because it is not represented by Git's regular-file index mode.

On non-POSIX platforms where the POSIX executable distinction is not reliably available through the local filesystem contract, untracked regular files normalize to `100644`. This keeps identity deterministic rather than inferring execution semantics from extensions, shell associations, or platform-specific heuristics.

Tracked-file mode changes remain represented by Git's own binary diff and are not reimplemented by Ronin.

## Fail-closed containment

Untracked capture remains repository-contained and fail closed:

- each discovered path must resolve successfully inside the repository root;
- the path itself is inspected with `lstat`;
- only regular files are accepted;
- symlinks, sockets, devices, FIFOs and other special files are rejected;
- unreadable files fail capture rather than being silently omitted.

The record order is deterministic and raw untracked content is not persisted in the revision identity.

## Compatibility note

Adding normalized mode to an untracked record means a dirty worktree containing untracked files may receive a different `dirty_patch_sha256` than older Ronin code even when its path and bytes are unchanged. This is intentional: the previous identity omitted behaviorally relevant executable state.

The namespace remains `ronin/git-dirty-v1` for v0.1 because this slice corrects an incomplete local-worktree identity rather than introducing a second public revision object. Release evidence should always record the exact Ronin SHA that produced the digest.

## Validation status

This implementation was reviewed under the maintainer's code-only policy. Automated tests and GitHub Actions were not executed. The existing real-Git regression suite must be extended and rerun when automated qualification is explicitly restored.
