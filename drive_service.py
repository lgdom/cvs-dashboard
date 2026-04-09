import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import os
import io
import pandas as pd

DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID")

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    """Autentica y devuelve el servicio de Drive usando st.secrets."""
    import json
    
    # 1. Intentar cargar desde Streamlit Secrets (Nube)
    if "gcp_service_account" in st.secrets:
        creds_data = st.secrets["gcp_service_account"]
        
        # Si Streamlit lo cargó como string (común si no es TOML puro), lo parseamos
        if isinstance(creds_data, str):
            try:
                creds_info = json.loads(creds_data)
            except Exception as e:
                raise ValueError(f"El secreto 'gcp_service_account' no es un JSON válido: {e}")
        else:
            # Si es un dict (TOML puro)
            creds_info = dict(creds_data)
            
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        
    else:
        # Fallback local para desarrollo
        file_sa = "service_account.json"
        if os.path.exists(file_sa) and not os.path.isdir(file_sa):
            creds = service_account.Credentials.from_service_account_file(file_sa, scopes=SCOPES)
        else:
            raise FileNotFoundError("No hay credenciales en st.secrets ni archivo 'service_account.json' válido.")
        
    return build('drive', 'v3', credentials=creds)

def find_file_in_folder(service, filename, folder_id):
    """Busca un archivo por nombre dentro de una carpeta específica."""
    query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    return None

def download_file_from_drive(local_path, drive_filename, folder_id=DRIVE_FOLDER_ID):
    """
    Descarga un archivo desde Drive dado su nombre y la carpeta ID.
    Si no existe, no hace nada (o retorna False).
    """
    try:
        # Asegurar que el directorio local existe (Crucial para Streamlit Cloud)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        service = get_drive_service()
        file_id = find_file_in_folder(service, drive_filename, folder_id)
        
        if not file_id:
            print(f"Archivo {drive_filename} no encontrado en Drive.")
            return False

        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()

        with open(local_path, 'wb') as f:
            f.write(fh.getbuffer())
            
        print(f"Descargado {drive_filename} a {local_path}")
        return True
    
    except Exception as e:
        st.error(f"Error de Persistencia: No se pudo escribir en {local_path}. Verifique permisos.")
        print(f"Error descargando {drive_filename}: {e}")
        return False

def upload_file_to_drive(local_path, drive_filename, folder_id=DRIVE_FOLDER_ID):
    """
    Sube (o actualiza) un archivo a Drive.
    """
    try:
        # Asegurar directorio local base por si acaso
        if os.path.dirname(local_path):
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
        service = get_drive_service()
        file_id = find_file_in_folder(service, drive_filename, folder_id)
        
        if not os.path.exists(local_path):
             return False, f"Archivo local {local_path} no encontrado para subir."

        media = MediaFileUpload(local_path, resumable=True)
        
        if file_id:
            # Actualizar existente
            service.files().update(fileId=file_id, media_body=media).execute()
            msg = f"Actualizado {drive_filename} (ID: {file_id})"
            print(msg)
        else:
            # Crear nuevo (Aunque el usuario ya subió los archivos, esto es por seguridad)
            file_metadata = {
                'name': drive_filename,
                'parents': [folder_id]
            }
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            msg = f"Creado {drive_filename}"
            print(msg)
            
        return True, msg
    except Exception as e:
        err_msg = f"Error subiendo {drive_filename}: {str(e)}"
        print(err_msg)
        return False, err_msg

def append_to_history_log(new_rows_df, drive_filename="historial_faltantes.csv", folder_id=None):
    """
    Lógica específica para añadir filas al historial CSV en Drive:
    1. Descarga el actual (si existe).
    2. Concatena los nuevos datos.
    3. Sube el archivo actualizado.
    """
    import tempfile
    
    # Usar un archivo temporal local
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        temp_path = tmp.name
        
    try:
        # 1. Intentar descargar existente
        exists = download_file_from_drive(temp_path, drive_filename, folder_id)
        
        if exists:
            # Leer existente
            try:
                df_hist = pd.read_csv(temp_path)
            except:
                 df_hist = pd.DataFrame()
        else:
            df_hist = pd.DataFrame()
            
        # 2. Concatenar
        df_updated = pd.concat([df_hist, new_rows_df], ignore_index=True)
        
        # Guardar localmente
        df_updated.to_csv(temp_path, index=False)
        
        # 3. Subir
        return upload_file_to_drive(temp_path, drive_filename, folder_id)
        
    finally:
        # Limpieza
        if os.path.exists(temp_path):
            os.remove(temp_path)

def reset_history_log(drive_filename="historial_faltantes.csv", folder_id=None):
    """
    Reinicia el historial en Drive subiendo un archivo CSV vacío con las cabeceras.
    """
    import tempfile
    cols = ['CODIGO', 'DESCRIPCION', 'SOLICITADA', 'SURTIDO', 'FECHA', 'CLIENTE']
    df_empty = pd.DataFrame(columns=cols)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        temp_path = tmp.name
        
    try:
        df_empty.to_csv(temp_path, index=False)
        return upload_file_to_drive(temp_path, drive_filename, folder_id)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def load_history_log(drive_filename="historial_faltantes.csv", folder_id=None):
    """
    Descarga y retorna el DataFrame del historial.
    """
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        temp_path = tmp.name
        
    try:
        exists = download_file_from_drive(temp_path, drive_filename, folder_id)
        if exists:
            return pd.read_csv(temp_path)
        else:
            return pd.DataFrame()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


import streamlit as st

def descargar_de_drive(folder_id):
    """
    Busca el archivo más reciente (CSV o XLSX) en la carpeta de Drive,
    lo descarga en memoria y devuelve (dataframe, nombre, fecha).
    Usa streamlit cache para no descargar a cada rato si no ha cambiado.
    """
    
    # Esta función interna es la que hace el trabajo pesado
    try:
        service = get_drive_service()
        # Listar archivos ordenados por fecha mod (desc)
        query = f"'{folder_id}' in parents and trashed = false and (mimeType = 'text/csv' or mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')"
        results = service.files().list(
            q=query, 
            orderBy="modifiedTime desc", 
            pageSize=1, 
            fields="files(id, name, modifiedTime, mimeType)").execute()
        files = results.get('files', [])
        
        if not files:
            return None, None, None
            
        latest = files[0]
        file_id = latest['id']
        name = latest['name']
        mod_time = latest.get('modifiedTime', '') # Fecha ISO
        
        # Descargar en memoria
        import io
        from googleapiclient.http import MediaIoBaseDownload
        
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        fh.seek(0)
        
        # Parsear
        if name.endswith('.csv'):
            try: df = pd.read_csv(fh, header=0, encoding='latin-1')
            except: fh.seek(0); df = pd.read_csv(fh, header=0, encoding='utf-8')
        else:
            try:
                df = pd.read_excel(fh, header=0, engine='calamine')
            except:
                df = pd.read_excel(fh, header=0)
            
        return df, name, mod_time
        
    except Exception as e:
        return None, f"Error: {str(e)}", None
