# 🧊 Therion BI Dashboard

Dashboard de Inteligencia de Negocios de última generación diseñado para auditar y visualizar el rendimiento comercial de **Therion ERP**. Este panel integra un scraper automatizado, persistencia en la nube vía Google Drive y visualizaciones interactivas de alto impacto con ECharts.

## 🚀 Características Principales

*   **Sincronización en un Clic**: Actualiza tus datos directamente desde el dashboard conectándote al ERP.
*   **Visualizaciones Premium**: Gráficos de tendencia, Pareto, Treemaps y Scatter Plots animados (0.5s de duración).
*   **KPIs con Sparklines**: Indicadores clave de rendimiento con visualización de tendencia integrada.
*   **Persistencia Híbrida**: Sincronización automática de datos maestros con Google Drive para persistencia en Streamlit Cloud.
*   **Seguridad Blindada**: Gestión de credenciales mediante `st.secrets`.

## 📂 Estructura del Proyecto

*   `dashboard.py`: Aplicación principal de Streamlit.
*   `scraper.py`: Motor de extracción de datos (web scraping) del ERP.
*   `drive_service.py`: Puente de conexión con la API de Google Drive.
*   `data/`: Directorio local de almacenamiento temporal (ignorable en Git).
*   `.streamlit/secrets.toml`: Configuración de secretos (No compartido en el repo).

## 🛠️ Configuración (Deploy en Streamlit Cloud)

1.  **Requisitos**: Sube estos archivos a tu repositorio de GitHub.
2.  **Secretos**: En el panel de Streamlit Cloud, configura las siguientes "Secrets":
    *   `THERION_USER`: Tu usuario del ERP.
    *   `THERION_PASS`: Tu contraseña del ERP.
    *   `DRIVE_FOLDER_ID`: El ID de tu carpeta de Google Drive.
    *   `gcp_service_account`: El contenido JSON de tu Service Account de Google.

## 💻 Instalación Local

```bash
# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar
streamlit run dashboard.py
```

---
**Desarrollado para Therion ERP Analytics.**
