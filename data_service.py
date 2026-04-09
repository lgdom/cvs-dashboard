import pandas as pd
import streamlit as st
from src.config import FILE_CLIENTES, FILE_PRODUCTOS

@st.cache_data
def cargar_catalogos():
    errores = []
    df_cli = pd.DataFrame()
    df_prod = pd.DataFrame()
    
    # 1. CLIENTES
    try:
        try: df_cli = pd.read_csv(FILE_CLIENTES, encoding='utf-8')
        except: df_cli = pd.read_csv(FILE_CLIENTES, encoding='latin-1')
        
        df_cli.columns = df_cli.columns.str.strip().str.upper()
        col_clave = next((c for c in df_cli.columns if 'CLAVE' in c or 'CODIGO' in c), df_cli.columns[0])
        col_nombre = next((c for c in df_cli.columns if ('CLIENTE' in c or 'NOMBRE' in c) and c != col_clave), df_cli.columns[1])
        
        df_cli = df_cli[[col_clave, col_nombre]].copy()
        df_cli.columns = ['CODIGO', 'NOMBRE']
        df_cli['DISPLAY'] = df_cli['CODIGO'].astype(str) + " - " + df_cli['NOMBRE'].astype(str)
    except Exception as e:
        errores.append(f"Clientes: {e}")

    # 2. PRODUCTOS (Catálogo Maestro)
    try:
        try: df_prod = pd.read_csv(FILE_PRODUCTOS, encoding='utf-8')
        except: df_prod = pd.read_csv(FILE_PRODUCTOS, encoding='latin-1')
            
        df_prod.columns = df_prod.columns.str.strip().str.upper()
        col_clave = next(c for c in df_prod.columns if 'CLAVE' in c or 'CODIGO' in c)
        col_desc = next(c for c in df_prod.columns if 'NOMBRE' in c or 'DESCRIPCION' in c)
        col_sust = next((c for c in df_prod.columns if 'SUSTANCIA' in c), None)
        
        cols = [col_clave, col_desc]
        if col_sust: cols.append(col_sust)
        df_prod = df_prod[cols].copy()
        
        nombres = ['CODIGO', 'DESCRIPCION']
        if col_sust: nombres.append('SUSTANCIA')
        df_prod.columns = nombres
        
        if 'SUSTANCIA' not in df_prod.columns: df_prod['SUSTANCIA'] = '---'
        else: df_prod['SUSTANCIA'] = df_prod['SUSTANCIA'].fillna('---')

        # --- LIMPIEZA AGRESIVA ---
        df_prod['CODIGO'] = df_prod['CODIGO'].astype(str).str.strip()
        df_prod = df_prod.drop_duplicates(subset=['CODIGO'], keep='first')
        df_prod = df_prod.dropna(subset=['DESCRIPCION'])

        # Índice de búsqueda optimizado
        df_prod['SEARCH_INDEX'] = (
            df_prod['CODIGO'] + " | " + 
            df_prod['DESCRIPCION'].astype(str) + " | " + 
            df_prod['SUSTANCIA'].astype(str)
        ).str.upper()
        
    except Exception as e:
        errores.append(f"Productos: {e}")

    return df_cli, df_prod, errores

def procesar_inventario(df_raw, df_productos):
    """
    Procesa el archivo crudo de inventario y lo cruza con el catálogo de productos.
    """
    # Normalizar nombres de columnas
    try:
        df_raw.columns = df_raw.columns.astype(str).str.strip().str.upper().str.replace('\n', '')
    except:
        pass

    # Buscar las columnas por su nombre actual o histórico
    col_sucursal = next((c for c in df_raw.columns if 'SUCURSAL' in c), None)
    col_localidad = next((c for c in df_raw.columns if 'LOCALIDAD' in c), None)
    col_codigo = next((c for c in df_raw.columns if 'CLAVE' in c or 'CODIGO' in c), None)
    col_prod = next((c for c in df_raw.columns if 'PRODUCTO' in c or 'DESCRIP' in c), None)
    col_exist = next((c for c in df_raw.columns if 'EXISTENCIA' in c or 'CANTIDAD' in c), None)
    col_cad = next((c for c in df_raw.columns if 'CADUCIDAD' in c or 'CORTA' in c), None)

    is_multi_format = any('TIJUANA' in str(c) for c in df_raw.columns)

    # 1. Intentar Procesamiento Formato Nuevo Multi-Columnas
    if is_multi_format:
        tijuana_idx = next(i for i, c in enumerate(df_raw.columns) if 'TIJUANA' in str(c))
        row0 = df_raw.iloc[0].astype(str).str.strip().str.upper().tolist()
        corta_idx, exist_idx = -1, -1
        for i in range(tijuana_idx, len(row0)):
            if corta_idx == -1 and 'CORTA' in row0[i]: corta_idx = i
            if exist_idx == -1 and 'EXISTENCIA' in row0[i]: exist_idx = i
            if corta_idx != -1 and exist_idx != -1: break
            
        df_tj = df_raw.iloc[1:, [0, 1, corta_idx, exist_idx]].copy()
        df_tj.columns = ['CODIGO', 'PRODUCTO', 'CORTA_CAD', 'EXISTENCIA']
        df_tj['EXISTENCIA'] = pd.to_numeric(df_tj['EXISTENCIA'], errors='coerce').fillna(0).astype(int)
        df_tj['CORTA_CAD'] = pd.to_numeric(df_tj['CORTA_CAD'], errors='coerce').fillna(0).astype(int)

    # 2. Intentar Procesamiento Formato (Múltiples sucursales y Localidad en filas)
    elif col_sucursal and col_localidad and col_codigo and col_exist:
        df_tj = df_raw[df_raw[col_sucursal].astype(str).str.contains('Tijuana', case=False, na=False)].copy()
        df_tj = df_tj.dropna(subset=[col_codigo])
        df_tj[col_codigo] = df_tj[col_codigo].astype(str).str.strip()
        df_tj[col_exist] = pd.to_numeric(df_tj[col_exist], errors='coerce').fillna(0)
        
        if col_prod:
            df_tj[col_prod] = df_tj[col_prod].astype(str).str.strip()
            idx = [col_codigo, col_prod]
        else:
            idx = [col_codigo]
            
        pivot = df_tj.pivot_table(
            index=idx, 
            columns=col_localidad, 
            values=col_exist, 
            aggfunc='sum', 
            fill_value=0
        ).reset_index()
        
        c_ventas = next((c for c in pivot.columns if 'VENTAS' in str(c).upper()), None)
        c_corta = next((c for c in pivot.columns if 'CORTA' in str(c).upper()), None)
        
        pivot['EXISTENCIA'] = pivot[c_ventas].astype(int) if c_ventas else 0
        pivot['CORTA_CAD'] = pivot[c_corta].astype(int) if c_corta else 0
        
        rename_cols = {col_codigo: 'CODIGO'}
        if col_prod: rename_cols[col_prod] = 'PRODUCTO'
        pivot.rename(columns=rename_cols, inplace=True)
        
        cols_finales_temp = ['CODIGO']
        if col_prod: cols_finales_temp.append('PRODUCTO')
        cols_finales_temp.extend(['EXISTENCIA', 'CORTA_CAD'])
        
        df_tj = pivot[cols_finales_temp].copy()

    # 3. Formato Clásico / Fallback
    else:
        if not all([col_codigo, col_prod, col_exist, col_cad]):
            try:
                df_tj = df_raw.iloc[:, [2, 3, 8, 5]].copy() # fallback
            except:
                if len(df_raw.columns) >= 7:
                    df_tj = df_raw.iloc[:, [0, 1, 5, 6]].copy() # fallback
                else:
                    return pd.DataFrame()
            df_tj.columns = ['CODIGO', 'PRODUCTO', 'CORTA_CAD', 'EXISTENCIA']
            df_tj['EXISTENCIA'] = pd.to_numeric(df_tj['EXISTENCIA'], errors='coerce').fillna(0).astype(int)
            df_tj['CORTA_CAD'] = pd.to_numeric(df_tj['CORTA_CAD'], errors='coerce').fillna(0).astype(int)
        else:
            df_tj = df_raw[[col_codigo, col_prod, col_cad, col_exist]].copy()
            df_tj.columns = ['CODIGO', 'PRODUCTO', 'CORTA_CAD', 'EXISTENCIA']
            df_tj['EXISTENCIA'] = pd.to_numeric(df_tj['EXISTENCIA'], errors='coerce').fillna(0).astype(int)
            df_tj['CORTA_CAD'] = pd.to_numeric(df_tj['CORTA_CAD'], errors='coerce').fillna(0).astype(int)

    df_tj = df_tj.dropna(subset=['CODIGO'])
    df_tj['CODIGO'] = df_tj['CODIGO'].astype(str).str.strip()

    # Unir con master de productos con `how='right'` para no perder artículos sin stock
    df_merged = pd.merge(df_tj, df_productos[['CODIGO', 'DESCRIPCION', 'SUSTANCIA']], on='CODIGO', how='right')
    
    # Rellenar valores que pudieran estar vacíos al no haber inventario
    df_merged['PRODUCTO'] = df_merged.get('PRODUCTO', df_merged['DESCRIPCION']).fillna(df_merged['DESCRIPCION'])
    df_merged['EXISTENCIA'] = df_merged['EXISTENCIA'].fillna(0).astype(int)
    df_merged['CORTA_CAD'] = df_merged['CORTA_CAD'].fillna(0).astype(int)
    df_merged['SUSTANCIA'] = df_merged['SUSTANCIA'].fillna('---')
    
    df_merged['INDICE_BUSQUEDA'] = (
        df_merged['CODIGO'] + " " + 
        df_merged['PRODUCTO'] + " " + 
        df_merged['SUSTANCIA']
    ).str.upper()

    cols_finales = ['CODIGO', 'PRODUCTO', 'SUSTANCIA', 'EXISTENCIA', 'CORTA_CAD', 'INDICE_BUSQUEDA']
    return df_merged[cols_finales]
