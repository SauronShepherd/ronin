"""Request/task actor propagation without global mutable identity state."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from collections.abc import Iterator

from .contracts import Actor

_CURRENT_ACTOR: ContextVar[Actor | None] = ContextVar("ronin_current_actor", default=None)


def current_actor() -> Actor | None:
    return _CURRENT_ACTOR.get()


def require_actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise PermissionError("authenticated actor is required")
    return actor


@contextmanager
def actor_context(actor: Actor) -> Iterator[Actor]:
    token: Token[Actor | None] = _CURRENT_ACTOR.set(actor)
    try:
        yield actor
    finally:
        _CURRENT_ACTOR.reset(token)


__all__ = ("actor_context", "current_actor", "require_actor")
