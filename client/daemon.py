import time
import os
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import json
from constants import *
from messages import FETCH_CHANGES, WATCHING
import client_services
from auth import authenticated_request, login, load_tokens


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {'last_sync': None, 'files': {}, 'versions': {}, 'hashes': {}}


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)


class SyncHandler(FileSystemEventHandler):
    def __init__(self):
        self.state = load_state()
        self.recently_created = set()
        self.downloading = set()
        self.last_event_time = {}

    def should_ignore(self, path):
        now = time.time()
        last = self.last_event_time.get(path, 0)
        if now - last < 1.0:
            return True
        self.last_event_time[path] = now
        return False

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path in self.downloading:
            return
        if self.should_ignore(event.src_path):
            return
        self.recently_created.add(event.src_path)
        self.state, _ = client_services.upload_file(event.src_path, self.state, is_new=True)
        save_state(self.state)

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path in self.downloading:
            return
        if event.src_path in self.recently_created:
            self.recently_created.discard(event.src_path)
            return
        if self.should_ignore(event.src_path):
            return
        self.state, _ = client_services.upload_file(event.src_path, self.state, is_new=False)
        save_state(self.state)

    def on_deleted(self, event):
        if event.is_directory:
            return
        self.state, _ = client_services.delete_file(event.src_path, self.state)
        save_state(self.state)

    def on_moved(self, event):
        if event.is_directory:
            return
        self.state, _ = client_services.rename_file(event.src_path, event.dest_path, self.state)
        save_state(self.state)


def fetch_changes(state, downloading, watched_folder):
    since = state.get('last_sync')
    params = f'?since={since}' if since else ''
    response = authenticated_request('GET', f'{SERVER_URL}/sync/changes{params}')

    if not response:
        return


    if response.status_code == 200:
        data = response.json()
        changes = data.get('changes', [])

        if changes:
            print(f'{len(changes)} {FETCH_CHANGES}')
            for change in changes:
                local_path = os.path.join(watched_folder, change['file_path'].lstrip('/'))
                downloading.add(local_path)
                state = client_services.apply_change(change, state)
                downloading.discard(local_path)
            state['last_sync'] = data['last_sync']
            save_state(state)


def is_new_client(state):
    return not state['files'] and state['last_sync'] is None


def authenticate():
    tokens = load_tokens()
    if tokens:
        print('using saved credentials.')
        return True

    print('--- login ---')
    username = input('username: ')
    password = input('password: ')

    tokens = login(username, password)
    if tokens:
        print('login successful.')
        return True
    else:
        print('login failed.')
        return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python daemon.py <folder_to_watch>')
        exit(1)
        
    if not authenticate():
        exit(1)

    WATCHED_FOLDER = os.path.abspath(sys.argv[1])
    client_services.WATCHED_FOLDER = WATCHED_FOLDER

    os.makedirs(WATCHED_FOLDER, exist_ok=True)

    handler = SyncHandler()

    if is_new_client(handler.state):
        handler.state = client_services.initialize(handler.state)
        save_state(handler.state)

    observer = Observer()
    observer.schedule(handler, WATCHED_FOLDER, recursive=True)
    observer.start()
    print(f'{WATCHING}: {WATCHED_FOLDER}')

    try:
        while True:
            fetch_changes(handler.state, handler.downloading, WATCHED_FOLDER)
            time.sleep(10)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
