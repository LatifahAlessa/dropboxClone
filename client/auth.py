import os
import json
import requests
from constants import SERVER_URL

TOKEN_FILE = 'tokens.json'


def load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            return json.load(f)
    return None


def save_tokens(tokens):
    with open(TOKEN_FILE, 'w') as f:
        json.dump(tokens, f)


def login(username, password):
    response = requests.post(
        f'{SERVER_URL}/auth/login/',
        json={'username': username, 'password': password}
    )

    if response.status_code == 200:
        tokens = response.json()
        save_tokens(tokens)
        return tokens
    else:
        print(f'login failed: {response.status_code} - {response.text}')
        return None


def refresh_access_token():
    tokens = load_tokens()
    if not tokens or 'refresh' not in tokens:
        return None

    response = requests.post(
        f'{SERVER_URL}/auth/token/refresh/',
        json={'refresh': tokens['refresh']}
    )

    if response.status_code == 200:
        new_access = response.json()['access']
        tokens['access'] = new_access
        save_tokens(tokens)
        return tokens
    else:
        return None


def get_auth_header():
    tokens = load_tokens()
    if not tokens:
        return None
    return {'Authorization': f'Bearer {tokens["access"]}'}


def authenticated_request(method, url, **kwargs):
    """Make a request with auth. Retry once with refreshed token on 401."""
    headers = kwargs.pop('headers', {})
    auth_header = get_auth_header()

    if not auth_header:
        print('not authenticated. please login first.')
        return None

    headers.update(auth_header)
    response = requests.request(method, url, headers=headers, **kwargs)

    if response.status_code == 401:
        refreshed = refresh_access_token()
        if refreshed:
            headers.update({'Authorization': f'Bearer {refreshed["access"]}'})
            response = requests.request(method, url, headers=headers, **kwargs)
        else:
            print('session expired. please login again.')
            return None

    return response
