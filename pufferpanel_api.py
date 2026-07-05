import requests
import json
import os
import glob
import gzip
from dotenv import load_dotenv

load_dotenv()
client_id = os.getenv('PUFFERPANEL_CLIENTID')
client_secret = os.getenv('PUFFERPANEL_SECRET')

url = os.getenv('PANEL_URL')
SERVERS_DIR = os.getenv('SERVERS_DIR', '/servers')


def get_header():
    request_data = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
    }

    r = requests.post(url + '/oauth2/token', data=request_data)
    token = r.json()['access_token']
    return {'Authorization': 'Bearer ' + token}


def get_user_info() -> json:
    r = requests.get(url + '/api/users', headers=get_header())
    return r.json()


def get_servers() -> dict:
    print('Getting servers')
    r = requests.get(url + '/api/servers', headers=get_header())
    name_to_id = dict()
    for server in r.json()['servers']:
        name_to_id[server['name']] = server['id']
    return name_to_id


def start_server(server_id: str):
    print('Starting server ' + server_id)
    requests.post(url + '/api/servers/' + server_id + '/start', params={}, headers=get_header())


def stop_server(server_id: str):
    print('Stopping server ' + server_id)
    requests.post(url + '/api/servers/' + server_id + '/stop', params={}, headers=get_header())


def get_server_status(server_id: str) -> bool:
    print(f"Getting server status for {server_id}")
    r = requests.get(f"{url}/api/servers/{server_id}/status", headers=get_header())

    if "application/json" not in (r.headers.get("Content-Type") or ""):
        raise RuntimeError("Expected JSON but got:\n" + r.text)

    data = r.json()
    return data["running"]


def get_server_logs(server_id: str) -> str:
    import base64
    print(f"Getting logs for {server_id}")
    r = requests.get(f"{url}/api/servers/{server_id}/console", headers=get_header())

    if "application/json" not in (r.headers.get("Content-Type") or ""):
        raise RuntimeError("Expected JSON but got:\n" + r.text)

    data = r.json()
    return base64.b64decode(data['logs']).decode('utf-8', errors='replace')


def list_log_files(server_id: str) -> list:
    log_dir = os.path.join(SERVERS_DIR, server_id, 'logs')
    if not os.path.isdir(log_dir):
        return []
    files = sorted(glob.glob(os.path.join(log_dir, '*.log')) + glob.glob(os.path.join(log_dir, '*.log.gz')))
    return [os.path.basename(f) for f in files]


def read_log_file(server_id: str, filename: str) -> str:
    filepath = os.path.join(SERVERS_DIR, server_id, 'logs', filename)
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Log file not found: {filename}")
    if filename.endswith('.gz'):
        with gzip.open(filepath, 'rt', errors='replace') as f:
            return f.read()
    with open(filepath, 'r', errors='replace') as f:
        return f.read()
