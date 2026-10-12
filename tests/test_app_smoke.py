"""Smoke test: the Streamlit app starts and shows the log-in / sign-up page without errors."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_login_page_renders():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Log in", "Sign up"]


def test_offline_first_login_error_message():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input[0].set_value("nobody")
    at.text_input[1].set_value("wrong")
    at.button[0].click().run()
    assert not at.exception
    assert len(at.error) >= 1  # unknown user: clear message, no crash
