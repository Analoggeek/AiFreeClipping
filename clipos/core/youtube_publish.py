"""Explicit-consent YouTube Data API publishing; tokens live in OS keychain.

Google OAuth client configuration is supplied by the channel owner/maintainer,
not embedded credentials. No network activity occurs until Connect or Upload.
"""
from pathlib import Path
import json

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
SERVICE = 'CLIPOS.YouTube'
ACCOUNT = 'channel-oauth'
DISCLAIMER = ('Edited with CLIPOS. Clip selection, captions and framing may be AI-assisted. '
              'Review context and accuracy. Attribution does not grant reuse rights.')


def upload_metadata(title, description, keywords=(), source_url='', privacy='private', made_for_kids=None, synthetic=False):
    if privacy not in ('private','unlisted','public'):
        raise ValueError('Choose a valid upload visibility')
    if made_for_kids is None:
        raise ValueError('You must declare whether this video is made for kids')
    title = ' '.join(str(title).replace('<','').replace('>','').split())[:100]
    if not title:
        raise ValueError('A title is required')
    tags, budget = [], 0
    for word in keywords:
        tag = ' '.join(str(word).replace('#','').split())[:60]
        cost = len(tag)+3
        if tag and tag.lower() not in {t.lower() for t in tags} and budget+cost <= 450:
            tags.append(tag)
            budget += cost
    description = str(description).replace('<','').replace('>','').strip()
    suffix = '\n\n' + DISCLAIMER
    if source_url.startswith(('https://youtube.com/', 'https://www.youtube.com/', 'https://youtu.be/')):
        suffix += '\nSource: ' + source_url[:300]
    suffix += '\n#Shorts #Gaming'
    # Keep comfortably inside the API's 5000-byte limit for all languages.
    available = 4900-len(suffix.encode('utf-8'))
    description = description.encode('utf-8')[:max(0,available)].decode('utf-8', errors='ignore')+suffix
    return {'snippet': {'title': title, 'description': description, 'tags': tags, 'categoryId': '20'},
            'status': {'privacyStatus': privacy, 'selfDeclaredMadeForKids': bool(made_for_kids),
                       'containsSyntheticMedia': bool(synthetic)}}


def _keyring():
    import keyring
    # Never fall back to insecure/plaintext keyrings.
    backend = keyring.get_keyring()
    module = type(backend).__module__
    if not module.startswith(('keyring.backends.macOS', 'keyring.backends.Windows', 'keyring.backends.SecretService', 'keyring.backends.kwallet')):
        raise RuntimeError('No supported secure OS keychain. Enable your system keychain before connecting YouTube.')
    return keyring


def connect(client_file):
    from google_auth_oauthlib.flow import InstalledAppFlow
    keychain = _keyring()  # Fail before opening consent if safe storage is unavailable.
    config = json.loads(Path(client_file).read_text(encoding='utf-8'))
    installed = config.get('installed', {})
    if installed.get('auth_uri') != 'https://accounts.google.com/o/oauth2/auth' or installed.get('token_uri') != 'https://oauth2.googleapis.com/token':
        raise ValueError('Choose the original Google OAuth Desktop app client JSON (not a web client)')
    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    credentials = flow.run_local_server(host='localhost', port=0, open_browser=True,
                                       timeout_seconds=180, access_type='offline', prompt='consent')
    keychain.set_password(SERVICE, ACCOUNT, credentials.to_json())
    return True


def disconnect():
    keychain = _keyring()
    if keychain.get_password(SERVICE, ACCOUNT):
        keychain.delete_password(SERVICE, ACCOUNT)


def credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    keychain = _keyring()
    data = keychain.get_password(SERVICE, ACCOUNT)
    if not data:
        raise RuntimeError('Connect your YouTube account first')
    creds = Credentials.from_authorized_user_info(json.loads(data), SCOPES)
    if not creds.valid:
        if not creds.refresh_token:
            raise RuntimeError('YouTube authorization expired. Connect again.')
        creds.refresh(Request())
        keychain.set_password(SERVICE, ACCOUNT, creds.to_json())
    return creds


def publish(path, body, progress=None, cancel=None):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0 or path.suffix.lower() != '.mp4':
        raise ValueError('Choose a real rendered MP4 clip')
    if cancel and cancel():
        raise RuntimeError('Upload cancelled')
    # Authorization/quota failures propagate to UI; never fake an upload ID.
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp
    service = build('youtube', 'v3', http=AuthorizedHttp(credentials(), http=httplib2.Http(timeout=60)), cache_discovery=False)
    try:
        request = service.videos().insert(part='snippet,status', body=body,
            media_body=MediaFileUpload(str(path), mimetype='video/mp4', chunksize=8*1024*1024, resumable=True))
        response = None
        while response is None:
            if cancel and cancel():
                raise RuntimeError('Upload cancelled; check YouTube Studio before retrying to avoid duplicates')
            status, response = request.next_chunk(num_retries=3)
            if status and progress:
                progress(status.progress()*100, 'Uploading to YouTube')
        if not response.get('id'):
            raise RuntimeError('YouTube returned no video ID. Check YouTube Studio before retrying.')
        return {'id': response['id'], 'url': 'https://www.youtube.com/watch?v='+response['id']}
    finally:
        service.close()
