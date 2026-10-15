from pathlib import Path

import pytest

from tools.compose_qualification import ComposeQualificationError, qualify_compose


def test_repository_compose_appliance_contract_is_qualified():
    assert qualify_compose(Path("compose.yaml"))


def test_compose_qualification_rejects_public_postgres_port(tmp_path):
    compose = (
        Path("compose.yaml")
        .read_text(encoding="utf-8")
        .replace("127.0.0.1:${RONIN_POSTGRES_PORT:-5432}:5432", "${RONIN_POSTGRES_PORT:-5432}:5432")
    )
    path = tmp_path / "compose.yaml"
    path.write_text(compose, encoding="utf-8")
    with pytest.raises(ComposeQualificationError, match="loopback"):
        qualify_compose(path)
