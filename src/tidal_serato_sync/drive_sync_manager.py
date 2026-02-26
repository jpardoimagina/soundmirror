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
    def __init__(self, credentials_path=None, token_path='token.json', log_path='upload_errors.log'):
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
        self.log_path = log_path
        self.base_source_dir = None
        self.service = self._authenticate()

    def _log_error(self, local_path, error_msg):
        """Guarda el error en el archivo de log."""
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(f"{local_path} | Error: {error_msg}\n")

    def _escape_q(self, name):
        """Escapa comillas simples para la query de Drive API."""
        return name.replace("'", "\\'")

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
        escaped_name = self._escape_q(folder_name)
        query = f"name = '{escaped_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
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
        escaped_name = self._escape_q(file_name)
        query = f"name = '{escaped_name}' and '{parent_id}' in parents and trashed = false"
        results = self.service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        return len(results.get('files', [])) > 0

    def upload_file(self, local_path, parent_id):
        """Sube un archivo a una carpeta de Drive."""
        file_name = os.path.basename(local_path)
        
        # Calcular path relativo para mostrar
        display_path = local_path
        if self.base_source_dir:
            try:
                display_path = os.path.relpath(local_path, self.base_source_dir)
            except ValueError:
                pass

        if self.file_exists(file_name, parent_id):
            print(f"Skipping: {display_path} (ya existe)")
            return

        print(f"Uploading: {display_path}...")
        try:
            file_metadata = {
                'name': file_name,
                'parents': [parent_id]
            }
            media = MediaFileUpload(local_path, resumable=True)
            self.service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        except Exception as e:
            print(f"❌ Error subiendo {display_path}: {e}")
            self._log_error(local_path, str(e))

    def sync_folder_recursive(self, local_dir, drive_parent_id, excludes=None, allowed_extensions=None):
        """Sincroniza recursivamente una carpeta local con Drive."""
        if self.base_source_dir is None:
            self.base_source_dir = str(Path(local_dir).resolve())

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
                # Filter by extension if allowed_extensions is provided
                if allowed_extensions:
                    # item.suffix includes the dot, e.g., '.mp3'
                    ext = item.suffix.lower().lstrip('.')
                    if ext not in [e.lower() for e in allowed_extensions]:
                        continue
                
                self.upload_file(str(item), drive_parent_id)
            elif item.is_dir():
                # Crear carpeta en Drive y seguir recursivamente
                subfolder_id = self.get_or_create_folder(item.name, drive_parent_id)
                self.sync_folder_recursive(item, subfolder_id, excludes, allowed_extensions)
