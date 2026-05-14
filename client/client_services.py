import os
import hashlib
import requests
from constants import SERVER_URL
from messages import *
from auth import authenticated_request

WATCHED_FOLDER = None


def get_file_hash(local_path):
    with open(local_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def upload_file(local_path, state, is_new):
    relative_path = '/' + os.path.relpath(local_path, WATCHED_FOLDER)
    file_id = state['files'].get(relative_path)
    current_version = 0

    if file_id:
        current_version = state['versions'].get(str(file_id), 0)
        current_hash = get_file_hash(local_path)
        stored_hash = state.get('hashes', {}).get(str(file_id))
        if stored_hash and current_hash == stored_hash:
            print(f'{UPLOAD_SKIPPED}: {relative_path}')
            return state, False

    with open(local_path, 'rb') as f:
        response = authenticated_request(
            'POST',
            f'{SERVER_URL}/files/',
            data={
                'path': relative_path,
                'name': os.path.basename(local_path),
            },
            files={'file': f},
            headers={'X-Client-Version': str(current_version)}
        )

    if not response:
        return state, False

    if response.status_code in (200, 201):
        data = response.json()
        state['files'][relative_path] = data['id']
        state['versions'][str(data['id'])] = data['current_version']
        state.setdefault('hashes', {})[str(data['id'])] = get_file_hash(local_path)
        print(f'{UPLOAD_SUCCESS}: {relative_path}')
        return state, True
    else:
        print(f'{UPLOAD_FAILED}: {response.status_code}')
        return state, False


def delete_file(local_path, state):
    relative_path = '/' + os.path.relpath(local_path, WATCHED_FOLDER)
    file_id = state['files'].get(relative_path)

    if not file_id:
        print(f'{DELETE_SKIPPED}: {relative_path}')
        return state, False

    response = authenticated_request('DELETE', f'{SERVER_URL}/files/{file_id}/')

    if not response:
        return state, False

    if response.status_code == 200:
        del state['files'][relative_path]
        state.get('hashes', {}).pop(str(file_id), None)
        print(f'{DELETE_SUCCESS}: {relative_path}')
        return state, True
    else:
        print(f'{DELETE_FAILED}: {response.status_code}')
        return state, False


def rename_file(old_path, new_path, state):
    old_relative = '/' + os.path.relpath(old_path, WATCHED_FOLDER)
    new_relative = '/' + os.path.relpath(new_path, WATCHED_FOLDER)
    file_id = state['files'].get(old_relative)

    if not file_id:
        print(f'{RENAME_SKIPPED}: {old_relative}')
        return state, False

    response = authenticated_request(
        'PATCH',
        f'{SERVER_URL}/files/{file_id}/',
        json={
            'new_path': new_relative,
            'new_name': os.path.basename(new_path)
        }
    )

    if not response:
        return state, False

    if response.status_code == 200:
        state['files'][new_relative] = file_id
        del state['files'][old_relative]
        print(f'{RENAME_SUCCESS}: {old_relative} → {new_relative}')
        return state, True
    else:
        print(f'{RENAME_FAILED}: {response.status_code}')
        return state, False


def download_from_server(file_id, local_path, state, file_path):
    response = authenticated_request('GET', f'{SERVER_URL}/files/{file_id}/download/')

    if not response:
        return

    if response.status_code != 200:
        print(f'{DOWNLOAD_FAILED}: {response.status_code}')
        return

    data = response.json()
    file_response = requests.get(data['download_url'])

    if file_response.status_code != 200:
        print(f'{DOWNLOAD_FAILED}: {file_response.status_code}')
        return

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, 'wb') as f:
        f.write(file_response.content)

    state.setdefault('hashes', {})[str(file_id)] = data.get('hash', '')
    print(f'{DOWNLOAD_SUCCESS}: {file_path}')


def apply_change(change, state):
    operation = change['operation_type']
    file_id = change['file']
    file_path = change['file_path']
    local_path = os.path.join(WATCHED_FOLDER, file_path.lstrip('/'))

    if operation in ('CREATE', 'MODIFY'):
        download_from_server(file_id, local_path, state, file_path)
        state['files'][file_path] = file_id
        state['versions'][str(file_id)] = change['version_num']

    elif operation == 'RESTORE':
        state['files'][file_path] = file_id
        state['versions'][str(file_id)] = change['version_num']
        download_from_server(file_id, local_path, state, file_path)
        print(f'restored: {file_path}')

    elif operation == 'DELETE':
        if os.path.exists(local_path):
            os.remove(local_path)
            print(f'{DELETE_SUCCESS}: {file_path}')
        if file_path in state['files']:
            del state['files'][file_path]

    elif operation == 'RENAME':
        new_path = change.get('file_path')
        new_name = change.get('file_name')

        old_path = None
        for path, fid in state['files'].items():
            if fid == file_id:
                old_path = path
                break

        if old_path and new_path and old_path != new_path:
            old_local_path = os.path.join(WATCHED_FOLDER, old_path.lstrip('/'))
            new_local_path = os.path.join(WATCHED_FOLDER, new_path.lstrip('/'))
            os.makedirs(os.path.dirname(new_local_path), exist_ok=True)
            if os.path.exists(old_local_path):
                os.rename(old_local_path, new_local_path)
                print(f'{RENAME_SUCCESS}: {old_path} → {new_path}')
            state['files'][new_path] = state['files'].pop(old_path)

    return state


def initialize(state):
    print(INITALIZING_CLIENT)

    response = authenticated_request('GET', f'{SERVER_URL}/files/')

    if not response:
        return state

    if response.status_code == 200:
        files = response.json()

        if not files:
            print(SERVER_EMPTY)
            state['last_sync'] = None
            return state

        print(f' downloading {len(files)} files from server...')

        for file in files:
            file_id = file['id']
            file_path = file['path']
            local_path = os.path.join(WATCHED_FOLDER, file_path.lstrip('/'))

            download_from_server(file_id, local_path, state, file_path)
            state['files'][file_path] = file_id
            state['versions'][str(file_id)] = file['current_version']

        state['last_sync'] = files[-1].get('last_modified_time')
        print(INITALIZING_SUCCESS)

    return state
