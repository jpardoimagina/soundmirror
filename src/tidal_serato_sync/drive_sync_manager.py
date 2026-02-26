import os
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload
from pathlib import Path

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive.metadata.readonly']

class DriveSyncManager:
    def __init__(self, credentials_path=None, token_path='token.json'):
        if credentials_path is None:
            # Primero buscamos en el directorio actual
            if os.path.exists('credentials.json'):
                self.credentials_path = 'credentials.json'
            else:
                # Si no, buscamos dentro del paquete
                self.credentials_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
        else:
            self.credentials_path = credentials_path
            
        self.token_path = token_path
        self.service = self._authenticate()

    def _authenticate(self):
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                creds = pickle.load(token)
        
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"No se encontró {self.credentials_path}. Por favor, descárgalo de Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)

        return build('drive', 'v3', credentials=creds)

    def get_or_create_folder(self, folder_name, parent_id=None):
        """Busca una carpeta por nombre y la crea si no existe."""
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        
        results = self.service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        items = results.get('files', [])

        if items:
            return items[0]['id']
        
        # Crear la carpeta
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]
        
        file = self.service.files().create(body=file_metadata, fields='id').execute()
        return file.get('id')

    def file_exists(self, file_name, parent_id):
        """Verifica si un archivo existe en una carpeta específica."""
        query = f"name = '{file_name}' and '{parent_id}' in parents and trashed = false"
        results = self.service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        return len(results.get('files', [])) > 0

    def upload_file(self, local_path, parent_id):
        """Sube un archivo a una carpeta de Drive."""
        file_name = os.path.basename(local_path)
        if self.file_exists(file_name, parent_id):
            print(f"Skipping: {file_name} (ya existe)")
            return

        print(f"Uploading: {file_name}...")
        file_metadata = {
            'name': file_name,
            'parents': [parent_id]
        }
        media = MediaFileUpload(local_path, resumable=True)
        self.service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    def sync_folder_recursive(self, local_dir, drive_parent_id, excludes=None):
        """Sincroniza recursivamente una carpeta local con Drive."""
        if excludes is None:
            excludes = ["*.crate", "_Serato_", "*.bak", ".DS_Store"]

        local_path = Path(local_dir)
        
        for item in local_path.iterdir():
            # Check excludes
            should_exclude = False
            for pattern in excludes:
                if item.match(pattern):
                    should_exclude = True
                    break
            
            if should_exclude:
                continue

            if item.is_file():
                self.upload_file(str(item), drive_parent_id)
            elif item.is_dir():
                # Crear carpeta en Drive y seguir recursivamente
                subfolder_id = self.get_or_create_folder(item.name, drive_parent_id)
                self.sync_folder_recursive(item, subfolder_id, excludes)
