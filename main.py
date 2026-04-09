import os
import time
from scraper import ScraperService
from analysis import generate_reports

def main():
    print("==================================================")
    print("   THERION ERP - BI ENGINE & PIPELINE EJECUTABLE  ")
    print("==================================================")
    
    # 1. Configuración de Credenciales
    USUARIO = os.getenv('THERION_USER', 'lgarcia')
    PASS = os.getenv('THERION_PASS', 'Garcia2025!')
    
    # 2. Inicializar Scraper con Motor Incremental (Memoria)
    scraper = ScraperService(USUARIO, PASS)
    if not scraper.login():
        print("Operación abortada por credenciales.")
        return
        
    start_time = time.time()
    
    # 3. Lógica Incremental: Traer Novedades y Actualizar CSVs Master
    # Puedes modificar la fecha según convenga. Por defecto explora desde un periodo razonable.
    nuevos_registros = scraper.get_facturas(fecha_inicio='01/10/2025')
    
    elapsed = time.time() - start_time
    print(f"Extracción completada en {elapsed:.2f} segundos.")
    
    # 4. Refrescar Reportes y Analytics con datos actualizados
    print("\nRegenerando Reporte Ejecutivo Automático...")
    generate_reports('data/facturas_historicas.csv')
    
if __name__ == '__main__':
    main()
