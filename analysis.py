import os
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

def clean_data(df):
    """Limpia los datos del DataFrame extraído."""
    # Filtrar renglones de paginación que tengan "12345..." u otros valores no deseados o nulos
    df = df.dropna(subset=['Folio', 'Importe'])
    df = df[~df['Folio'].astype(str).str.contains('12345', na=False)]
    df = df[df['Folio'].astype(str).str.strip() != '']
    
    # Mantener solo las facturas Procesadas y Cerradas
    df = df[df['Situación'].isin(['Procesada', 'Cerrada'])]
    
    # Limpiar columna de Importe ($ y comas)
    df['ImporteNum'] = df['Importe'].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
    df['ImporteNum'] = pd.to_numeric(df['ImporteNum'], errors='coerce').fillna(0)
    
    # Limpiar fechas (ej. 27/03/2026 07:10:04 a. m.)
    def parse_fecha(f):
        try:
            # Eliminamos el formato a. m. / p. m. para algo parseable, o usamos el formato general de pandas
            f = f.replace('a. m.', 'AM').replace('p. m.', 'PM').replace('a.m.', 'AM').replace('p.m.', 'PM')
            return pd.to_datetime(f, format='%d/%m/%Y %I:%M:%S %p')
        except:
            return pd.to_datetime(f, errors='coerce', dayfirst=True)
            
    df['Fecha Limpia'] = df['Fecha'].apply(parse_fecha)
    df['Mes-Año'] = df['Fecha Limpia'].dt.to_period('M')
    return df

def generate_reports(csv_path):
    if not os.path.exists(csv_path):
        print(f"Error: No se encontró el archivo de datos en {csv_path}")
        return
        
    df_raw = pd.read_csv(csv_path)
    df = clean_data(df_raw)
    
    if df.empty:
        print("No hay datos suficientes para analizar después de la limpieza.")
        return
        
    # --- ANÁLISIS 1: Tendencia de Facturación (Mes a Mes) ---
    tendencia_mensual = df.groupby('Mes-Año')['ImporteNum'].sum()
    
    plt.figure(figsize=(10, 6))
    ax = tendencia_mensual.plot(kind='bar', color='skyblue', edgecolor='black')
    
    # Añadir montos como etiquetas
    for i, v in enumerate(tendencia_mensual):
        ax.text(i, v + (v*0.01), f'${v:,.2f}', ha='center', va='bottom', fontweight='bold')
        
    plt.title('Tendencia de Facturación Mensual', fontsize=16, fontweight='bold')
    plt.xlabel('Mes', fontsize=12)
    plt.ylabel('Monto Facturado ($)', fontsize=12)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('data/tendencia_mensual.png', dpi=300)
    plt.close()
    
    # --- ANÁLISIS 2: Top 5 Clientes ---
    top_clientes = df.groupby('Cliente')['ImporteNum'].sum().sort_values(ascending=False).head(5)
    
    plt.figure(figsize=(10, 6))
    ax2 = top_clientes.sort_values().plot(kind='barh', color='salmon', edgecolor='black')
    for i, v in enumerate(top_clientes.sort_values()):
        ax2.text(v + (v*0.01), i, f'${v:,.2f}', va='center', fontweight='bold')
        
    plt.title('Top 5 Clientes por Facturación', fontsize=16, fontweight='bold')
    plt.xlabel('Monto Facturado ($)', fontsize=12)
    plt.ylabel('Cliente', fontsize=12)
    plt.tight_layout()
    plt.savefig('data/top_clientes.png', dpi=300)
    plt.close()
    
    # --- ANÁLISIS 3: Top 10 Productos por Volumen (Cantidad Vendida) ---
    if os.path.exists('data/detalle_productos.csv'):
        # Leer y limpiar datos de productos
        df_prod = pd.read_csv('data/detalle_productos.csv')
        df_prod['CantidadNum'] = pd.to_numeric(df_prod['Cantidad'], errors='coerce').fillna(0)
        df_prod['ImporteProdNum'] = pd.to_numeric(df_prod['Importe'], errors='coerce').fillna(0)
        
        top_prod_vol = df_prod.groupby('Descripcion')['CantidadNum'].sum().sort_values(ascending=False).head(10)
        
        plt.figure(figsize=(12, 6))
        ax3 = top_prod_vol.sort_values().plot(kind='barh', color='mediumseagreen', edgecolor='black')
        for i, v in enumerate(top_prod_vol.sort_values()):
            ax3.text(v + (v*0.01), i, f'{int(v)}', va='center', fontweight='bold')
            
        plt.title('Top 10 Productos por Volumen (Unidades Vendidas)', fontsize=16, fontweight='bold')
        plt.xlabel('Unidades Vendidas', fontsize=12)
        plt.ylabel('Producto', fontsize=12)
        plt.tight_layout()
        plt.savefig('data/top_productos_volumen.png', dpi=300)
        plt.close()

        # --- ANÁLISIS 4: Top 10 Productos más Rentables (Monto Facturado) ---
        top_prod_rent = df_prod.groupby('Descripcion')['ImporteProdNum'].sum().sort_values(ascending=False).head(10)
        plt.figure(figsize=(12, 6))
        ax4 = top_prod_rent.sort_values().plot(kind='barh', color='gold', edgecolor='black')
        for i, v in enumerate(top_prod_rent.sort_values()):
            ax4.text(v + (v*0.01), i, f'${v:,.2f}', va='center', fontweight='bold')
            
        plt.title('Top 10 Productos por Rentabilidad (Monto $)', fontsize=16, fontweight='bold')
        plt.xlabel('Ingreso Generado ($)', fontsize=12)
        plt.ylabel('Producto', fontsize=12)
        plt.tight_layout()
        plt.savefig('data/top_productos_rentabilidad.png', dpi=300)
        plt.close()

    # --- Resumen Ejecutivo ---
    total_facturado = df['ImporteNum'].sum()
    total_pedidos = len(df)
    ticket_promedio = total_facturado / total_pedidos if total_pedidos > 0 else 0
    
    print("==================================================")
    print("      REPORTE EJECUTIVO DE VENTAS - THERION       ")
    print("==================================================")
    print(f"Total Facturado Histórico: ${total_facturado:,.2f}")
    print(f"Total de Facturas (Procesadas/Cerradas): {total_pedidos}")
    print(f"Ticket Promedio: ${ticket_promedio:,.2f}")
    
    if os.path.exists('data/detalle_productos.csv'):
        tot_unidades = df_prod['CantidadNum'].sum()
        total_prods_unicos = df_prod['Descripcion'].nunique()
        print(f"Total de Unidades Vendidas: {int(tot_unidades)}")
        print(f"Catálogo Vendido (Prod. Únicos): {total_prods_unicos}")
        print("--------------------------------------------------")
        
        # --- AUDITORÍA Y CUADRE DE DATOS ---
        print("                 AUDITORÍA DE DATOS               ")
        folios_fac = set(df['Folio'].unique())
        # Filtrar df_prod a las facturas válidas procesadas para cuadrar
        df_prod_valido = df_prod[df_prod['Folio'].isin(folios_fac)]
        folios_prod = set(df_prod_valido['Folio'].unique())
        
        faltantes = folios_fac - folios_prod
        print(f"Folios Válidos en Catálogo Mestro: {len(folios_fac)}")
        print(f"Folios Conciliados (con desglose de pzs): {len(folios_prod)}")
        if not faltantes:
            print("Estado de Extracción: 100% (SIN OMISIONES)")
        else:
            print(f"Estado: EXISTEN {len(faltantes)} FACTURAS NO DESCARGADAS. Ej: {list(faltantes)[:3]}")
        
    print("--------------------------------------------------")
    print("Gráficos generados en la carpeta /data/:")
    print(" - tendencia_mensual.png")
    print(" - top_clientes.png")
    if os.path.exists('data/detalle_productos.csv'):
        print(" - top_productos_volumen.png")
        print(" - top_productos_rentabilidad.png")
    print("==================================================")

if __name__ == '__main__':
    generate_reports('data/facturas_historicas.csv')
