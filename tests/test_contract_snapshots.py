import hashlib

import pytest
from studio_core import DiagnosticPredicate, OperatorPort, builtin_diagnostic_catalog, builtin_operator_catalog


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_builtin_catalogs_preserve_complete_portable_contract_snapshots() -> None:
    assert _sha256(builtin_operator_catalog().to_json()) == (
        "d68227c8cc293f749fc771b4c6526054c9eae9b254fd007e56778525110563a8"
    )
    assert _sha256(builtin_diagnostic_catalog().to_json()) == (
        "e6261bd71fa5935c2d260bad3833ee18f96e0e943391700f6463881d421f66c7"
    )


def test_portable_metadata_text_boundaries_are_explicit() -> None:
    OperatorPort("x" * 500)
    DiagnosticPredicate("message", "contains", "x" * 500)

    with pytest.raises(ValueError, match="line breaks"):
        OperatorPort("bad\rname")
    with pytest.raises(ValueError, match="line breaks"):
        DiagnosticPredicate("message", "contains", "bad\rvalue")
