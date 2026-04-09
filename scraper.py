import os
import requests
import urllib3
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import time
import html

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ScraperService:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.base_url = 'https://therion.victory-enterprises.com'
        self.login_url = f'{self.base_url}/LoginLTE.aspx'
        self.facturas_url = f'{self.base_url}/Autentificados/Ventas/Documentos/Facturas.aspx'
        self.data_dir = 'data'
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        # --- CARGAR MEMORIA DE EJECUCIÓN (MARCADOR) ---
        self.facturas_csv = os.path.join(self.data_dir, 'facturas_historicas.csv')
        self.productos_csv = os.path.join(self.data_dir, 'detalle_productos.csv')
        
        self.folios_procesados = set()
        if os.path.exists(self.facturas_csv):
            try:
                df_exist = pd.read_csv(self.facturas_csv)
                self.folios_procesados = set(df_exist['Folio'].astype(str).tolist())
                print(f"Memoria cargada: {len(self.folios_procesados)} facturas previas identificadas.")
            except:
                pass

    def _get_viewstate(self, soup=None, xml_text=None):
        if xml_text:
            soup = BeautifulSoup(xml_text, 'html.parser')
        viewstate = soup.find('input', {'name': '__VIEWSTATE'})
        generator = soup.find('input', {'name': '__VIEWSTATEGENERATOR'})
        validation = soup.find('input', {'name': '__EVENTVALIDATION'})
        return {
            '__VIEWSTATE': viewstate['value'] if viewstate else '',
            '__VIEWSTATEGENERATOR': generator['value'] if generator else '',
            '__EVENTVALIDATION': validation['value'] if validation else ''
        }

    def login(self):
        print("Iniciando sesión en Therion ERP...")
        response = self.session.get(self.login_url, verify=False)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        data = self._get_viewstate(soup)
        data.update({
            'ctl00$ContentPlaceHolder1$txtUsuario': self.username,
            'ctl00$ContentPlaceHolder1$txtPassword': self.password,
            'ctl00$ContentPlaceHolder1$loginButton': 'Ingresar'
        })
        
        response_post = self.session.post(self.login_url, data=data, verify=False)
        if 'LoginLTE.aspx' not in response_post.url:
            print("Login exitoso.")
            return True
        print("Error en el login.")
        return False

    def parse_cfdi_xml(self, xml_content, folio):
        products = []
        try:
            soup = BeautifulSoup(xml_content, 'lxml-xml')
            conceptos = soup.find_all('Concepto')
            for c in conceptos:
                products.append({
                    'Folio': folio,
                    'ClaveProdServ': c.get('ClaveProdServ', ''),
                    'NoIdentificacion': c.get('NoIdentificacion', ''),
                    'Cantidad': c.get('Cantidad', '0'),
                    'ClaveUnidad': c.get('ClaveUnidad', ''),
                    'Unidad': c.get('Unidad', ''),
                    'Descripcion': c.get('Descripcion', ''),
                    'ValorUnitario': c.get('ValorUnitario', '0'),
                    'Importe': c.get('Importe', '0')
                })
        except Exception as e:
            print(f"Error parseando CFDI {folio}: {e}")
        return products

    def get_facturas(self, fecha_inicio='01/10/2025', fecha_fin=None):
        if fecha_fin is None:
            fecha_fin = datetime.now().strftime('%d/%m/%Y')
            
        print(f"Buscando nuevas facturas desde {fecha_inicio} al {fecha_fin}...")
        resp = self.session.get(self.facturas_url, verify=False)
        soup = BeautifulSoup(resp.text, 'html.parser')

        form_data = self._get_viewstate(soup)
        for input_el in soup.find_all('input'):
            name = input_el.get('name')
            if name and name not in form_data and input_el.get('type') not in ['submit', 'button', 'image', 'checkbox', 'radio']:
                form_data[name] = input_el.get('value', '')

        form_data['ctl00$MainContent$txtFechaInicio'] = fecha_inicio
        form_data['ctl00$MainContent$txtFechaFin'] = fecha_fin
        
        post_data = form_data.copy()
        post_data['ctl00$MainContent$btnActualizar'] = 'Actualizar'
        
        resp_search = self.session.post(self.facturas_url, data=post_data, verify=False)
        return self._process_pages(resp_search, post_data)

    def _process_pages(self, resp_search, base_post_data):
        all_dfs = []
        all_products = []
        page = 1
        
        while True:
            print(f"Escaneando página {page} explorando novedades...")
            soup_page = BeautifulSoup(resp_search.text, 'html.parser')
            
            try:
                import io
                dfs = pd.read_html(io.StringIO(resp_search.text), flavor='html5lib')
                main_df = None
                for df in dfs:
                    if len(df) > 2 and len(df.columns) > 5:
                        main_df = df
                        break
                        
                if main_df is None:
                    break

                # Filtrar ruido de paginación
                main_df = main_df.dropna(subset=['Folio', 'Situación'])
                estatus_validos = ['Procesada', 'Cerrada', 'Cancelada']
                main_df = main_df[main_df['Situación'].isin(estatus_validos)]
                main_df = main_df[main_df['Folio'].astype(str).str.match(r'^\d+$', na=False)]
                
                # REVISIÓN DE MEMORIA - Filtrar solo lo nuevo
                df_nuevo = main_df[~main_df['Folio'].astype(str).isin(self.folios_procesados)]
                
                if not df_nuevo.empty:
                    all_dfs.append(df_nuevo)
                
                # Optimization Break: Si esta página ya no tiene NINGÚN registro nuevo y no es la primera, 
                # significa que ya tocamos el histórico escrapeado (las nuevas salen arriba).
                if df_nuevo.empty and page > 1:
                    print("Se alcanzó el límite histórico de la memoria. Ignorando páginas restantes para ahorrar tiempo...")
                    break
                
                # --- EXTRACCIÓN DE PRODUCTOS (SOLO NUEVOS) ---
                grid = soup_page.find('table', {'id': 'MainContent_gridPrincipal'})
                if grid:
                    trs = grid.find_all('tr')
                    for tr in trs:
                        situacion = tr.find('span', {'class': 'label'})
                        if situacion and situacion.text.strip() in estatus_validos:
                            tds = tr.find_all('td')
                            if len(tds) > 3:
                                folio_val = tds[2].text.strip()
                                
                                # Saltar descargas intensivas si ya lo tenemos
                                if str(folio_val) in self.folios_procesados:
                                    continue
                                    
                                cb = tr.find('input', {'type': 'checkbox'})
                                if cb:
                                    print(f" [+] Descargando CFDI de nueva factura: {folio_val}")
                                    cb_name = cb.get('name')
                                    xml_post = base_post_data.copy()
                                    xml_post.update(self._get_viewstate(soup_page))
                                    if 'ctl00$MainContent$btnActualizar' in xml_post:
                                        del xml_post['ctl00$MainContent$btnActualizar']
                                    
                                    xml_post[cb_name] = 'on'
                                    xml_post['__EVENTTARGET'] = 'ctl00$MenuContent$menuStrip'
                                    xml_post['__EVENTARGUMENT'] = 'XML'
                                    
                                    r_xml_gen = self.session.post(self.facturas_url, data=xml_post, verify=False)
                                    soup_xml_gen = BeautifulSoup(r_xml_gen.text, 'html.parser')
                                    xml_href = None
                                    for a in soup_xml_gen.find_all('a'):
                                        if 'xml' in a.text.lower():
                                            xml_href = a.get('href')
                                            break
                                            
                                    if xml_href and 'Visor.aspx' in xml_href:
                                        xml_href = html.unescape(xml_href)
                                        url_xls = 'https://therion.victory-enterprises.com/Autentificados/Reporteador/' + xml_href.split('/Reporteador/')[1]
                                        r_xls = self.session.get(url_xls, verify=False)
                                        
                                        # VALIDACIÓN CRÍTICA: Asegurarse de que no sea una página HTML de error/login
                                        if r_xls.status_code == 200 and b'<!DOCTYPE html>' not in r_xls.content[:100]:
                                            prods = self.parse_cfdi_xml(r_xls.content, folio_val)
                                            all_products.extend(prods)
                                        else:
                                            print(f" [!] Error en descarga de CFDI {folio_val}: Respuesta no válida del ERP.")
                                    time.sleep(0.3)


                # Paginación
                has_next = False
                links = soup_page.find_all('a')
                for link in links:
                    href = link.get('href', '')
                    if f"Page${page+1}" in href:
                        has_next = True
                        break
                        
                if not has_next:
                    break
                    
                state = self._get_viewstate(soup_page)
                base_post_data.update(state)
                if 'ctl00$MainContent$btnActualizar' in base_post_data:
                    del base_post_data['ctl00$MainContent$btnActualizar']
                base_post_data['__EVENTTARGET'] = 'ctl00$MainContent$gridPrincipal'
                base_post_data['__EVENTARGUMENT'] = f'Page${page+1}'
                
                resp_search = self.session.post(self.facturas_url, data=base_post_data, verify=False)
                page += 1
                
            except ValueError:
                break
                
        # Guardar / Actualizar Persistencia
        nuevos_reg = 0
        if all_dfs:
            final_df = pd.concat(all_dfs, ignore_index=True)
            cols_to_drop = [c for c in final_df.columns if pd.isna(c) or 'Unnamed' in c]
            final_df.drop(columns=cols_to_drop, inplace=True)
            nuevos_reg = len(final_df)
            
            # Anexar al archivo existente o crear nuevo
            if os.path.exists(self.facturas_csv):
                old_df = pd.read_csv(self.facturas_csv)
                merged = pd.concat([old_df, final_df]).drop_duplicates(subset=['Folio'], keep='last')
                merged.to_csv(self.facturas_csv, index=False, encoding='utf-8-sig')
            else:
                final_df.to_csv(self.facturas_csv, index=False, encoding='utf-8-sig')
                
        if all_products:
            prod_df = pd.DataFrame(all_products)
            if os.path.exists(self.productos_csv):
                old_prod = pd.read_csv(self.productos_csv)
                merged_prod = pd.concat([old_prod, prod_df]).drop_duplicates()
                merged_prod.to_csv(self.productos_csv, index=False, encoding='utf-8-sig')
            else:
                prod_df.to_csv(self.productos_csv, index=False, encoding='utf-8-sig')
                
        if nuevos_reg > 0:
            print(f"Extracción finalizada: ¡Se añadieron {nuevos_reg} facturas nuevas a la base de datos local!")
        else:
            print("Tu base de datos está totalmente al día y sincronizada. No hubo facturas nuevas.")
            
        return nuevos_reg
