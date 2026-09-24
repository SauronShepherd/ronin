from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


class _DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.head = 0
        self.body = 0
        self.module_sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "head":
            self.head += 1
        elif tag == "body":
            self.body += 1
        elif tag == "script" and attributes.get("type") == "module":
            source = attributes.get("src")
            if source is not None:
                self.module_sources.append(source)


def test_studio_index_has_one_valid_document_and_unique_module_bootstrap() -> None:
    parser = _DocumentParser()
    parser.feed((Path("web") / "index.html").read_text(encoding="utf-8"))

    assert parser.head == 1
    assert parser.body == 1
    assert parser.module_sources
    assert len(parser.module_sources) == len(set(parser.module_sources))
    assert all(source.startswith("./js/") for source in parser.module_sources)
