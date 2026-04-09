import streamlit as st
import pandas as pd
from streamlit_echarts import st_echarts
import os
from scraper import ScraperService
import time
from drive_service import download_file_from_drive, upload_file_to_drive

# --- Configuración Visual ---
st.set_page_config(
    page_title="Therion ERP | BI Dashboard",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Estilización Base ---
# Usamos el estilo nativo de Streamlit
st.markdown("""
<style>
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_data():
    fac_path = 'data/facturas_historicas.csv'
    prod_path = 'data/detalle_productos.csv'
    
    # --- PERSISTENCIA EN NUBE ---
    # Si los archivos no existen (primera vez en la nube), intentamos traerlos de Drive
    if not os.path.exists(fac_path):
        with st.spinner("Sincronizando base de datos desde la nube..."):
            download_file_from_drive(fac_path, 'facturas_historicas.csv')
            download_file_from_drive(prod_path, 'detalle_productos.csv')
    
    df_fac = pd.DataFrame()
    df_prod = pd.DataFrame()
    
    if os.path.exists(fac_path):
        df_fac = pd.read_csv(fac_path)
        # Limpieza básica facturas
        df_fac['ImporteNum'] = df_fac['Importe'].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
        df_fac['ImporteNum'] = pd.to_numeric(df_fac['ImporteNum'], errors='coerce').fillna(0)
        def parse_fecha(f):
            try:
                f = str(f).replace('a. m.', 'AM').replace('p. m.', 'PM').replace('a.m.', 'AM').replace('p.m.', 'PM')
                return pd.to_datetime(f, format='%d/%m/%Y %I:%M:%S %p', errors='coerce')
            except:
                return pd.to_datetime(f, errors='coerce', dayfirst=True)
        df_fac['Fecha Limpia'] = df_fac['Fecha'].apply(parse_fecha)
        # Valid files only
        df_fac = df_fac[df_fac['Situación'].isin(['Procesada', 'Cerrada'])]

    if os.path.exists(prod_path):
        df_prod = pd.read_csv(prod_path)
        df_prod['CantidadNum'] = pd.to_numeric(df_prod['Cantidad'], errors='coerce').fillna(0)
        df_prod['ImporteProdNum'] = pd.to_numeric(df_prod['Importe'], errors='coerce').fillna(0)
        
    return df_fac, df_prod

# Cargar Datos
df, df_prod = load_data()

# --- SIDEBAR ---
#st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3068/3068224.png", width=100)
st.sidebar.title("Therion Analytics")
#st.sidebar.markdown("Filtrado de Datos")

if not df.empty:
    # Filtro de Fechas
    min_date = df['Fecha Limpia'].min().date()
    max_date = df['Fecha Limpia'].min().date() if pd.isna(df['Fecha Limpia'].max()) else df['Fecha Limpia'].max().date()
    
    date_range = st.sidebar.date_input("Rango de Fechas", [min_date, max_date])
    if len(date_range) == 2:
        df = df[(df['Fecha Limpia'].dt.date >= date_range[0]) & (df['Fecha Limpia'].dt.date <= date_range[1])]

    # Filtro de Cliente
    clientes = ['Todos'] + sorted(df['Cliente'].dropna().unique().tolist())
    cliente_sel = st.sidebar.selectbox("Filtro por Cliente", clientes)
    if cliente_sel != 'Todos':
        df = df[df['Cliente'] == cliente_sel]
        
    # Sincronizar df_prod
    folios_filtrados = set(df['Folio'].astype(str).tolist())
    df_prod = df_prod[df_prod['Folio'].astype(str).isin(folios_filtrados)]

# --- BOTÓN DE ACTUALIZACIÓN (SCRAPER) ---
st.sidebar.divider()
st.sidebar.subheader("Sincronización")
if st.sidebar.button("🔄 Actualizar Datos de Therion", use_container_width=True):
    with st.sidebar.status("Conectando con Therion ERP...", expanded=True) as status:
        try:
            # Configuración de Credenciales (Seguridad estricta: Solo vía st.secrets)
            USUARIO = st.secrets.get("THERION_USER")
            PASS = st.secrets.get("THERION_PASS")
            
            if not USUARIO or not PASS:
                status.update(label="❌ Error: Credenciales no configuradas en los Secretos de la App.", state="error")
                st.stop()
            
            scraper = ScraperService(USUARIO, PASS)
            if scraper.login():
                status.update(label="Login exitoso. Buscando facturas nuevas...", state="running")
                nuevos = scraper.get_facturas(fecha_inicio='01/10/2025')
                
                if nuevos > 0:
                    status.update(label="Subiendo respaldo a la nube (Google Drive)...", state="running")
                    upload_file_to_drive('data/facturas_historicas.csv', 'facturas_historicas.csv')
                    upload_file_to_drive('data/detalle_productos.csv', 'detalle_productos.csv')
                    status.update(label=f"¡Éxito! Se añadieron {nuevos} facturas y se respaldaron en Drive.", state="complete", expanded=False)
                else:
                    status.update(label="Todo al día. No hay datos nuevos.", state="complete", expanded=False)
                
                # Forzar recarga de datos
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()
            else:
                status.update(label="Error de autenticación.", state="error")
        except Exception as e:
            status.update(label=f"Error: {str(e)}", state="error")

# --- CUERPO PRINCIPAL ---
st.title("Panel de Ventas (Ensenada)")
#st.markdown("Visualiza y audita el rendimiento comercial de la empresa en tiempo real.")

if df.empty:
    st.warning("No hay datos disponibles para los filtros seleccionados o el Scraper no ha sido ejecutado.")
    st.stop()

# --- KPIs ---
def create_sparkline(data, color):
    x_data = [str(i) for i in range(len(data))]
    return {
        "animation": True,
        "animationDuration": 500,
        "animationDurationUpdate": 500,
        "animationEasing": "cubicOut",
        "xAxis": {"type": "category", "data": x_data, "show": False, "boundaryGap": False},
        "yAxis": {"type": "value", "show": False, "scale": True},
        "grid": {"top": 10, "bottom": 10, "left": 0, "right": 0},
        "tooltip": {
            "trigger": "axis",
            "confine": True,
            "formatter": "{c}",
            "textStyle": {"fontSize": 12},
            "position": "bottom",
            "padding": [5, 10],
            "extraCssText": "box-shadow: 0 4px 10px rgba(0,0,0,0.1); border-radius: 8px;"
        },
        "series": [{
            "data": data,
            "type": "line",
            "showSymbol": False,
            "areaStyle": {"opacity": 0.1, "color": color},
            "lineStyle": {"color": color, "width": 2},
            "itemStyle": {"color": color}
        }]
    }

df_kpi = df.set_index('Fecha Limpia').resample('W').agg(
    Ingresos=('ImporteNum', 'sum'),
    Ticket=('ImporteNum', 'mean'),
    Clientes=('Cliente', 'nunique')
).reset_index().fillna(0)

spark_ing = [round(v, 2) for v in df_kpi['Ingresos'].tolist()[-12:]] if len(df_kpi) > 0 else []
spark_tic = [round(v, 2) for v in df_kpi['Ticket'].tolist()[-12:]] if len(df_kpi) > 0 else []
spark_cli = [round(v, 2) for v in df_kpi['Clientes'].tolist()[-12:]] if len(df_kpi) > 0 else []

spark_uni = []
if not df_prod.empty:
    df_pdt = pd.merge(df_prod.assign(Folio=df_prod['Folio'].astype(str)), df[['Folio', 'Fecha Limpia']].assign(Folio=df['Folio'].astype(str)), on='Folio')
    df_uni = df_pdt.set_index('Fecha Limpia').resample('W')['CantidadNum'].sum().reset_index().fillna(0)
    spark_uni = [round(v, 2) for v in df_uni['CantidadNum'].tolist()[-12:]]

def calc_delta(lst):
    if len(lst) >= 2 and lst[-2] != 0:
        return f"{((lst[-1] - lst[-2]) / lst[-2]) * 100:+.1f}%"
    return "0%"

c1, c2, c3, c4 = st.columns(4)
total_sales = df['ImporteNum'].sum()
avg_ticket = total_sales / len(df) if len(df) > 0 else 0
tot_units = df_prod['CantidadNum'].sum() if not df_prod.empty else 0
tot_clients = df['Cliente'].nunique()

try:
    with c1.container(border=True):
        st.metric("Ingresos Totales", f"${total_sales:,.0f}")
        st_echarts(theme="streamlit", options=create_sparkline(spark_ing, "#00E676"), height="60px", key="sp1")
    with c2.container(border=True):
        st.metric("Ticket Promedio", f"${avg_ticket:,.0f}")
        st_echarts(theme="streamlit", options=create_sparkline(spark_tic, "#00B0FF"), height="60px", key="sp2")
    with c3.container(border=True):
        st.metric("Unidades Movidas", f"{int(tot_units):,}")
        st_echarts(theme="streamlit", options=create_sparkline(spark_uni, "#FFC400"), height="60px", key="sp3")
    with c4.container(border=True):
        st.metric("Clientes Activos", f"{tot_clients}")
        st_echarts(theme="streamlit", options=create_sparkline(spark_cli, "#FF3D00"), height="60px", key="sp4")
except TypeError:
    with c1:
        st.metric("Ingresos Totales", f"${total_sales:,.0f}")
        st_echarts(theme="streamlit", options=create_sparkline(spark_ing, "#00E676"), height="60px", key="sp1f")
    with c2:
        st.metric("Ticket Promedio", f"${avg_ticket:,.0f}")
        st_echarts(theme="streamlit", options=create_sparkline(spark_tic, "#00B0FF"), height="60px", key="sp2f")
    with c3:
        st.metric("Unidades Movidas", f"{int(tot_units):,}")
        st_echarts(theme="streamlit", options=create_sparkline(spark_uni, "#FFC400"), height="60px", key="sp3f")
    with c4:
        st.metric("Clientes Activos", f"{tot_clients}")
        st_echarts(theme="streamlit", options=create_sparkline(spark_cli, "#FF3D00"), height="60px", key="sp4f")

st.markdown("<br>", unsafe_allow_html=True)

col_a, col_b = st.columns(2)

with col_a:
    df_trend = df.set_index('Fecha Limpia').resample('W')['ImporteNum'].sum().reset_index()
    # Echarts Area Chart
    st.markdown(f"#### Tendencia de Ingresos (Semanal)")
    options_fig1 = {
        "animation": True,
        "animationDuration": 500,
        "animationDurationUpdate": 500,
        "animationThreshold": 5000,
        "animationEasing": "cubicOut",
        "dataZoom": [{"type": "inside", "xAxisIndex": 0}, {"type": "slider", "xAxisIndex": 0, "bottom": 10}],
        "tooltip": {"trigger": "axis"},
        "xAxis": {
            "type": "category",
            "data": df_trend['Fecha Limpia'].dt.strftime('%Y-%m-%d').tolist()
        },
        "yAxis": {"type": "value"},
        "series": [{
            "data": df_trend['ImporteNum'].tolist(),
            "type": "line",
            "areaStyle": {"opacity": 0.3}
        }],
        "toolbox": {
            "feature": {
                "saveAsImage": {"show": True, "title": "Descargar", "name": "grafico"},
                "dataView": {"show": True, "readOnly": True, "title": "Datos Raw", "lang": ['Datos Raw', 'Cerrar', 'Actualizar']},
                "restore": {"show": True, "title": "Restaurar"}
            }
        }
    }
    st_echarts(options=options_fig1, height="350px", theme="streamlit", key="options_fig1")

with col_b:
    df_cli = df.groupby('Cliente')['ImporteNum'].sum().sort_values().tail(7).reset_index()
    st.markdown(f"#### Top 7 Clientes Más Valiosos")
    options_fig2 = {
        "animation": True,
        "animationDuration": 500,
        "animationDurationUpdate": 500,
        "animationThreshold": 5000,
        "animationEasing": "cubicOut",
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
        "xAxis": {"type": "value"},
        "yAxis": {
            "type": "category",
            "data": df_cli['Cliente'].str[:20].tolist()
        },
        "series": [{
            "type": "bar",
            "data": df_cli['ImporteNum'].tolist(),
            "itemStyle": {"borderRadius": [0, 5, 5, 0]}
        }],
        "toolbox": {
            "feature": {
                "saveAsImage": {"show": True, "title": "Descargar", "name": "grafico"},
                "dataView": {"show": True, "readOnly": True, "title": "Datos Raw", "lang": ['Datos Raw', 'Cerrar', 'Actualizar']},
                "restore": {"show": True, "title": "Restaurar"}
            }
        }
    }
    st_echarts(options=options_fig2, height="350px", theme="streamlit", key="options_fig2")

# --- GRÁFICOS DE PRODUCTOS (FILA 2) ---
if not df_prod.empty:
    col_c, col_d = st.columns(2)
    
    with col_c:
        prod_rent = df_prod.groupby('Descripcion')['ImporteProdNum'].sum().sort_values(ascending=False).head(10).reset_index()
        treemap_data = [{"name": row['Descripcion'][:15], "value": row['ImporteProdNum']} for idx, row in prod_rent.iterrows()]
        st.markdown(f"#### Top 10 Gasto/Rentabilidad")
        options_fig3 = {
            "animation": True,
            "animationDuration": 500,
            "animationDurationUpdate": 500,
            "animationThreshold": 5000,
            "animationEasing": "cubicOut",
            "tooltip": {"trigger": "item", "formatter": "{b}: ${c}"},
            "series": [{
                "type": "treemap",
                "data": treemap_data,
                "label": {"show": True, "formatter": "{b}"},
                "itemStyle": {"borderWidth": 0, "gapWidth": 5},
                "roam": False
            }],
            "toolbox": {
                "feature": {
                    "saveAsImage": {"show": True, "title": "Descargar", "name": "grafico"},
                    "dataView": {"show": True, "readOnly": True, "title": "Datos Raw", "lang": ['Datos Raw', 'Cerrar', 'Actualizar']},
                    "restore": {"show": True, "title": "Restaurar"}
                }
            }
        }
        st_echarts(options=options_fig3, height="350px", theme="streamlit", key="options_fig3")
        
    with col_d:
        prod_vol = df_prod.groupby('Descripcion')['CantidadNum'].sum().sort_values(ascending=False).head(10).reset_index()
        pie_data = [{"name": row['Descripcion'][:15], "value": row['CantidadNum']} for idx, row in prod_vol.iterrows()]
        st.markdown(f"#### Distribución Volumen (Top 10)")
        options_fig4 = {
            "animation": True,
            "animationDuration": 500,
            "animationDurationUpdate": 500,
            "animationThreshold": 5000,
            "animationEasing": "cubicOut",
            "tooltip": {"trigger": "item"},
            "series": [{
                "type": "pie",
                "radius": ["40%", "75%"],
                "data": [{"name": str(d["name"]), "value": float(d["value"])} for d in pie_data],
                "avoidLabelOverlap": True,
                "padAngle": 5,
                "itemStyle": {
                    "borderRadius": 10,
                    "borderColor": "#fff",
                    "borderWidth": 5,
                },
                "label": {
                    "show": True,
                    "position": "outside",
                    "formatter": "{b}",
                    "fontSize": 11
                },
                "labelLine": {"show": True, "length": 15, "length2": 10},
            }],
            "toolbox": {
                "feature": {
                    "saveAsImage": {"show": True, "title": "Descargar", "name": "grafico"},
                    "dataView": {"show": True, "readOnly": True, "title": "Datos Raw", "lang": ['Datos Raw', 'Cerrar', 'Actualizar']},
                    "restore": {"show": True, "title": "Restaurar"}
                }
            }
        }
        st_echarts(options=options_fig4, height="350px", theme="streamlit", key="options_fig4")

# --- VISTAS DETALLADAS ---
st.markdown("### Vistas Analíticas Especiales")
opcion_vista = st.radio(
    "Seleccione la vista a explorar:",
    ["Rendimiento por Producto", "Preferencias por Cliente", "Análisis de Pareto", "Facturas Maestro", "Detalle CGL"],
    horizontal=True,
    label_visibility="collapsed"
)

if opcion_vista == "Rendimiento por Producto":
    if not df_prod.empty:
        # Agrupar catálogo general
        rendimiento = df_prod.groupby('Descripcion').agg(
            Unidades_Vendidas=('CantidadNum', 'sum'),
            Ingreso_Generado=('ImporteProdNum', 'sum')
        ).reset_index()
        
        # Eliminar productos con 0 ventas si los hay
        rendimiento = rendimiento[rendimiento['Unidades_Vendidas'] > 0]
        
        scatter_data = [[row['Unidades_Vendidas'], row['Ingreso_Generado'], row['Descripcion']] for idx, row in rendimiento.iterrows()]
        st.markdown(f"#### Distribución Rendimiento")
        options_scatter = {
            "animation": True,
            "animationDuration": 500,
            "animationDurationUpdate": 500,
            "animationThreshold": 5000,
            "animationEasing": "cubicOut",
            "dataZoom": [{"type": "inside", "xAxisIndex": 0}, {"type": "slider", "xAxisIndex": 0, "bottom": 10}],
            "tooltip": {
                "formatter": "{c}"
            },
            "grid": {"left": "10%", "right": "10%", "bottom": "15%", "containLabel": True},
            "xAxis": {"type": "value", "name": "Unidades"},
            "yAxis": {"type": "value", "name": "Ingreso ($)"},
            "visualMap": {
                "show": False,
                "dimension": 0,
                "min": 0,
                "max": float(rendimiento['Unidades_Vendidas'].max()) if not rendimiento.empty else 100,
                "inRange": {"symbolSize": [10, 40]}
            },
            "series": [{
                "type": "scatter",
                "data": scatter_data
            }],
            "toolbox": {
                "feature": {
                    "saveAsImage": {"show": True, "title": "Descargar", "name": "grafico"},
                    "dataView": {"show": True, "readOnly": True, "title": "Datos Raw", "lang": ['Datos Raw', 'Cerrar', 'Actualizar']},
                    "restore": {"show": True, "title": "Restaurar"}
                }
            }
        }
        st_echarts(options=options_scatter, height="500px", theme="streamlit", key="options_scatter")
        
        st.markdown("---")
        st.markdown("#### Detalle de Rendimiento por Producto")
        st.dataframe(
            rendimiento.sort_values('Ingreso_Generado', ascending=False), 
            use_container_width=True, 
            hide_index=True,
            height=400,
            column_config={
                "Descripcion": st.column_config.TextColumn("Producto", width="medium"),
                "Unidades_Vendidas": st.column_config.NumberColumn("Unidades", format="%d"),
                "Ingreso_Generado": st.column_config.ProgressColumn(
                    "Ingreso Total",
                    format="$%.2f",
                    min_value=0,
                    max_value=float(rendimiento['Ingreso_Generado'].max())
                )
            }
        )

elif opcion_vista == "Preferencias por Cliente":
    if not df_prod.empty and not df.empty:
        # Hacer merge de df_prod con df_fac para obtener el Cliente por Folio
        # Aseguramos que Folio es string para cruzar correcto en ambos dataframes
        df_cli_prod = pd.merge(
            df_prod.assign(Folio=df_prod['Folio'].astype(str)), 
            df[['Folio', 'Cliente']].copy().assign(Folio=df['Folio'].astype(str)), 
            on='Folio', 
            how='inner'
        )
        
        # Opciones interactivas
        top_clientes_nombres = df['Cliente'].value_counts().index.tolist()
        sel_tab_cliente = st.selectbox("Seleccione el Cliente para analizar:", top_clientes_nombres)
        
        if sel_tab_cliente:
            df_filtrado_cli = df_cli_prod[df_cli_prod['Cliente'] == sel_tab_cliente]
            
            if not df_filtrado_cli.empty:
                prefs = df_filtrado_cli.groupby('Descripcion').agg(
                    Pedidas=('CantidadNum', 'sum'),
                    Gasto_Total=('ImporteProdNum', 'sum')
                ).reset_index().sort_values('Pedidas', ascending=False)
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    prefs_top = prefs.head(10).sort_values('Pedidas')
                    st.markdown(f"#### Top 10 Pedidos")
                    options_cli_prod = {
                        "animation": True,
                        "animationDuration": 500,
                        "animationDurationUpdate": 500,
                        "animationThreshold": 5000,
                        "animationEasing": "cubicOut",
                        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                        "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                        "xAxis": {"type": "value"},
                        "yAxis": {
                            "type": "category", 
                            "data": prefs_top['Descripcion'].str[:20].tolist()
                        },
                        "series": [{
                            "type": "bar",
                            "data": prefs_top['Pedidas'].tolist(),
                            "itemStyle": {"borderRadius": [0, 5, 5, 0]}
                        }],
                        "toolbox": {
                            "feature": {
                                "saveAsImage": {"show": True, "title": "Descargar", "name": "grafico"},
                                "dataView": {"show": True, "readOnly": True, "title": "Datos Raw", "lang": ['Datos Raw', 'Cerrar', 'Actualizar']},
                                "restore": {"show": True, "title": "Restaurar"}
                            }
                        }
                    }
                    st_echarts(options=options_cli_prod, height="400px", theme="streamlit", key="options_cli_prod")
                with col_c2:
                    st.markdown(f"**Análisis de Cartera de {sel_tab_cliente}**")
                    st.dataframe(
                        prefs, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "Descripcion": st.column_config.TextColumn("Producto"),
                            "Pedidas": st.column_config.NumberColumn("Total Pedido", format="%d"),
                            "Gasto_Total": st.column_config.NumberColumn("Inversión Total", format="$%.2f")
                        }
                    )
            else:
                st.info("Este cliente aún no registra productos específicos en el rango seleccionado.")

elif opcion_vista == "Análisis de Pareto":
    if not df_prod.empty:
        # Calcular Pareto de Productos por Importe
        df_pareto = df_prod.groupby('Descripcion')['ImporteProdNum'].sum().reset_index()
        df_pareto = df_pareto.sort_values(by='ImporteProdNum', ascending=False)
        df_pareto['Porcentaje_Acumulado'] = (df_pareto['ImporteProdNum'].cumsum() / df_pareto['ImporteProdNum'].sum()) * 100
        
        # Filtramos para no tener 100 productos si la cola es muy larga, solo los principales o todos si son < 50
        max_bars = 50 if len(df_pareto) > 50 else len(df_pareto)
        df_pareto_c = df_pareto.head(max_bars)
        st.markdown(f"#### Diagrama de Pareto")
        options_pareto = {
            "animation": True,
            "animationDuration": 500,
            "animationDurationUpdate": 500,
            "animationThreshold": 5000,
            "animationEasing": "cubicOut",
            "dataZoom": [{"type": "inside"}, {"type": "slider", "bottom": 10}],
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
            "legend": {"data": ["Ingreso ($)", "Acumulado (%)"], "top": "bottom"},
            "grid": {"left": "5%", "right": "5%", "bottom": "20%", "containLabel": True},
            "xAxis": [
                {
                    "type": "category",
                    "data": df_pareto_c['Descripcion'].str[:15].tolist(),
                    "axisPointer": {"type": "shadow"},
                    "axisLabel": {"rotate": 45}
                }
            ],
            "yAxis": [
                {
                    "type": "value",
                    "name": "Ingresos ($)"
                },
                {
                    "type": "value",
                    "name": "Acumulado",
                    "min": 0,
                    "max": 105,
                    "axisLabel": {"formatter": "{value} %"},
                    "splitLine": {"show": False}
                }
            ],
            "series": [
                {
                    "name": "Ingreso ($)",
                    "type": "bar",
                    "data": [float(x) for x in df_pareto_c['ImporteProdNum'].tolist()]
                },
                {
                    "name": "Acumulado (%)",
                    "type": "line",
                    "yAxisIndex": 1,
                    "data": [round(float(x), 2) for x in df_pareto_c['Porcentaje_Acumulado'].tolist()],
                    "markLine": {
                        "data": [{"yAxis": 80, "name": "80%"}],
                        "lineStyle": {"type": "dashed"}
                    }
                }
            ],
            "toolbox": {
                "feature": {
                    "saveAsImage": {"show": True, "title": "Descargar", "name": "grafico"},
                    "dataView": {"show": True, "readOnly": True, "title": "Datos Raw", "lang": ['Datos Raw', 'Cerrar', 'Actualizar']},
                    "restore": {"show": True, "title": "Restaurar"}
                }
            }
        }
        st_echarts(options=options_pareto, height="500px", theme="streamlit", key="options_pareto")


elif opcion_vista == "Facturas Maestro":
    st.dataframe(
        df.drop(columns=['ImporteNum', 'Fecha Limpia'], errors='ignore'), 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "Folio": st.column_config.TextColumn("Folio #"),
            "Importe": st.column_config.NumberColumn("Monto", format="$%.2f"),
            "Fecha": st.column_config.DatetimeColumn("Fecha de Emisión"),
            "Situación": st.column_config.SelectboxColumn("Estatus", options=["Procesada", "Cerrada", "Cancelada"])
        }
    )

elif opcion_vista == "Detalle CGL":
    if not df_prod.empty:
        st.dataframe(df_prod.drop(columns=['CantidadNum', 'ImporteProdNum'], errors='ignore'), use_container_width=True, hide_index=True)
