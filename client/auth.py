import os
import json
import requests
from constants import SERVER_URL
from messages import LOGIN_FAILED, NOT_AUTHENTICATED, SESSION_EXPIRED

TOKEN_FILE = "tokens.json"


def load_tokens():
    if not os.path.exists(TOKEN_FILE):
        return None

    with open(TOKEN_FILE, "r") as f:
        return json.load(f)


def save_tokens(tokens):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f)


def login(username, password):
    response = requests.post(
        f"{SERVER_URL}/auth/login/", json={"username": username, "password": password}
    )

    if response.status_code != 200:
        print(f"{LOGIN_FAILED}: {response.status_code} - {response.text}")
        return None

    tokens = response.json()
    save_tokens(tokens)
    return tokens


def refresh_access_token():
    tokens = load_tokens()
    if not tokens or "refresh" not in tokens:
        return None

    response = requests.post(
        f"{SERVER_URL}/auth/token/refresh/", json={"refresh": tokens["refresh"]}
    )

    if response.status_code != 200:
        return None

    tokens["access"] = response.json()["access"]
    save_tokens(tokens)
    return tokens


def authenticated_request(method, url, headers=None, **kwargs):
    if headers is None:
        headers = {}
    tokens = load_tokens()

    if not tokens:
        print(NOT_AUTHENTICATED)
        return None

    headers["Authorization"] = f'Bearer {tokens["access"]}'
    response = requests.request(method, url, headers=headers, **kwargs)

    if response.status_code != 401:
        return response

    refreshed = refresh_access_token()
    if not refreshed:
        print(SESSION_EXPIRED)
        return None

    headers["Authorization"] = f'Bearer {refreshed["access"]}'
    return requests.request(method, url, headers=headers, **kwargs)
