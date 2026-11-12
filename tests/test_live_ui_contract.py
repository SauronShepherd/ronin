from pathlib import Path


def test_connection_submit_persists_session_atomically_with_config() -> None:
    app = Path("web/js/app.js").read_text(encoding="utf-8")
    assert "const nextToken=clearToken?'':enteredToken||config.token" in app
    assert "setConfig(document.querySelector('#api-url').value.trim(),nextToken)" in app
    assert "if(nextToken)sessionStorage.setItem('ronin.session',nextToken);else sessionStorage.removeItem('ronin.session')" in app
