from pathlib import Path

REQUIRED_SEMANTIC_TOKENS = {
    "--ronin-color-primary",
    "--ronin-color-primary-hover",
    "--ronin-color-primary-active",
    "--ronin-color-accent",
    "--ronin-color-surface",
    "--ronin-color-surface-raised",
    "--ronin-color-text",
    "--ronin-color-text-muted",
    "--ronin-color-border",
    "--ronin-color-focus",
}


def test_brand_semantic_tokens_are_machine_readable() -> None:
    root = Path(__file__).resolve().parents[1]
    tokens = (root / "web/styles/tokens.css").read_text(encoding="utf-8")
    for token in REQUIRED_SEMANTIC_TOKENS:
        assert f"{token}:" in tokens
    assert "--ronin-color-primary: var(--copper);" in tokens
    assert "--ronin-color-focus: var(--focus);" in tokens


def test_main_studio_loads_the_shared_token_contract_before_components() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "web/index.html").read_text(encoding="utf-8")
    token_link = html.index('href="./styles/tokens.css"')
    component_link = html.index('href="./styles/components.css"')
    assert token_link < component_link
