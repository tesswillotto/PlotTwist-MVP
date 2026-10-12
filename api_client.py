"""Thin wrapper the Streamlit app uses to call the FastAPI engine."""
import requests

import config


def _headers(role: str) -> dict:
    return {"X-User-Role": role}


def signup(username, password, full_name, contact):
    """Returns (ok, user_dict_or_error_text)."""
    try:
        r = requests.post(f"{config.API_URL}/auth/signup", timeout=8, json={
            "username": username, "password": password,
            "full_name": full_name, "contact": contact})
    except requests.RequestException:
        return False, "Cannot reach the server. Sign-up needs an internet connection."
    return (True, r.json()) if r.status_code == 200 else (False, r.json().get("detail", "Sign-up failed."))


def login(username, password):
    """Online login (first time on this device). Returns (ok, user_dict_or_error_text)."""
    try:
        r = requests.post(f"{config.API_URL}/auth/login", timeout=8,
                          json={"username": username, "password": password})
    except requests.RequestException:
        return False, "Cannot reach the server."
    return (True, r.json()) if r.status_code == 200 else (False, r.json().get("detail", "Login failed."))


def get_json(path: str, role: str, **params):
    r = requests.get(f"{config.API_URL}{path}", headers=_headers(role), params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def get_bytes(path: str, role: str, **params) -> bytes:
    r = requests.get(f"{config.API_URL}{path}", headers=_headers(role), params=params, timeout=20)
    r.raise_for_status()
    return r.content
