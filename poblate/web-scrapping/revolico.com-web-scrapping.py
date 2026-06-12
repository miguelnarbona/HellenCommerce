import requests
from bs4 import BeautifulSoup
import sqlite3
import json
from datetime import datetime
import shutil
import argparse
import os
import logging

# -----------------------------------------------------------
# Ejemplo de uso:
#   python scraper.py --site revolico --desde-fecha 2026-04-15
# -----------------------------------------------------------

# --- Configuración de logging ---
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_COPY = os.path.join(BASE_DIR, "hellencommerce_copy.db")
DB_ORIGINAL = os.path.join(BASE_DIR, "hellencommerce.db")
DB_NAME = "revolico.db"

# --- Inicialización de la base ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        user_id TEXT PRIMARY KEY,
        nombre TEXT,
        telefono TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS marketplace (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        categoria TEXT,
        subcategoria TEXT,
        nombre TEXT,
        precio REAL,
        currency TEXT,
        ubicacion TEXT,
        telefono TEXT,
        whatsapp INTEGER,
        imagen TEXT,
        destacado INTEGER,
        vistas INTEGER,
        timestamp TEXT,
        contexto TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS categorias (
        id_categoria TEXT PRIMARY KEY,
        titulo TEXT,
        slug TEXT,
        id_padre TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS provincias_municipios (
        province_id TEXT,
        province_name TEXT,
        municipality_id TEXT,
        municipality_name TEXT,
        PRIMARY KEY (province_id, municipality_id)
    )""")
    conn.commit()
    conn.close()
    logging.info("Base de datos inicializada correctamente.")
    print("[INFO] Base de datos inicializada correctamente.")

# --- Backup antes de sincronizar ---
def backup_original_db():
    if os.path.exists(DB_ORIGINAL):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"hellencommerce_copy_{timestamp}.db"
        shutil.copy(DB_ORIGINAL, backup_name)
        logging.info(f"Backup creado: {backup_name}")
        print(f"[INFO] Backup creado: {backup_name}")
        return backup_name
    else:
        logging.warning("No existe la base original, se creará en la sincronización.")
        print("[WARN] No existe la base original, se creará en la sincronización.")
        return None

# --- Sincronización ---
def sincronizar_con_base_original():
    backup_original_db()
    src_conn = sqlite3.connect(DB_NAME)
    dst_conn = sqlite3.connect(DB_ORIGINAL)
    src_cur = src_conn.cursor()
    dst_cur = dst_conn.cursor()
    init_db()

    usuarios_count = 0
    marketplace_count = 0

    for row in src_cur.execute("SELECT * FROM usuarios"):
        dst_cur.execute("INSERT OR REPLACE INTO usuarios VALUES (?, ?, ?)", row)
        usuarios_count += 1

    for row in src_cur.execute("SELECT * FROM marketplace"):
        dst_cur.execute("""INSERT OR REPLACE INTO marketplace 
        (id, user_id, categoria, subcategoria, nombre, precio, currency,
        ubicacion, telefono, whatsapp, imagen, destacado, vistas, timestamp, contexto)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", row)
        marketplace_count += 1

    dst_conn.commit()
    src_conn.close()
    dst_conn.close()
    logging.info(f"Sincronización completada: {usuarios_count} usuarios, {marketplace_count} anuncios copiados.")
    print(f"[INFO] Sincronización completada: {usuarios_count} usuarios, {marketplace_count} anuncios copiados.")

# --- Cargar diccionarios desde __APOLLO_STATE__ ---
def cargar_diccionarios(data):
    municipios_dict = {}
    provincias_dict = {}
    categorias_dict = {}
    apollo = data.get("apolloState", data.get("__APOLLO_STATE__", {}))

    for key, value in apollo.items():
        if key.startswith("ProvinceType:"):
            provincias_dict[value["id"]] = value["name"]
            for ref in value.get("municipalities", []):
                mun_key = ref["__ref"]
                mun = apollo.get(mun_key)
                if mun:
                    municipios_dict[mun["id"]] = mun["name"]

    for key, value in apollo.items():
        if key.startswith("CategoryType:"):
            categorias_dict[value["slug"]] = value["title"]

    logging.info(f"Diccionarios cargados: {len(provincias_dict)} provincias, {len(municipios_dict)} municipios, {len(categorias_dict)} categorías.")
    print(f"[INFO] Diccionarios cargados: {len(provincias_dict)} provincias, {len(municipios_dict)} municipios, {len(categorias_dict)} categorías.")
    return municipios_dict, provincias_dict, categorias_dict

# --- Mostrar categorías y seleccionar ---
def seleccionar_categorias(categorias_dict):
    print("\n[INFO] Categorías disponibles:")
    slugs = list(categorias_dict.keys())
    for i, slug in enumerate(slugs, 1):
        print(f"{i}. {categorias_dict[slug]} (slug: {slug})")

    seleccion = input("\nSeleccione categorías a scrapear:\n - 0 para todas\n - números separados por coma (ej: 1,3,5)\n> ")

    if seleccion.strip() == "0":
        return slugs
    else:
        indices = [int(x.strip()) for x in seleccion.split(",") if x.strip().isdigit()]
        return [slugs[i-1] for i in indices if 0 < i <= len(slugs)]

# --- Scraper ---
def scrape_revolico(url, sync=False, categorias_seleccionadas=None, desde_fecha=None):
    if sync:
        sincronizar_con_base_original()
        return

    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
    data = json.loads(script_tag.string)

    municipios_dict, provincias_dict, categorias_dict = cargar_diccionarios(data)

    # Si no se pasó selección, pedirla en consola
    if categorias_seleccionadas is None:
        categorias_seleccionadas = seleccionar_categorias(categorias_dict)

    for slug in categorias_seleccionadas:
        print(f"\n[INFO] Scrapear categoría: {categorias_dict[slug]} ({slug})")
        url_cat = f"https://www.revolico.com/search?category={slug}"
        resp_cat = requests.get(url_cat)
        soup_cat = BeautifulSoup(resp_cat.text, "html.parser")
        script_tag_cat = soup_cat.find("script", {"id": "__NEXT_DATA__"})
        data_cat = json.loads(script_tag_cat.string)
        ads = data_cat["props"]["pageProps"]["staticPropsFeed"]["feed"]["edges"]

        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        ads_count = 0
        skipped_count = 0

        for ad in ads:
            node = ad["node"]
            user_id = node["id"]
            title = node["title"]
            price = node.get("price")
            currency = node.get("currency")
            permalink = node["permalink"]  # contexto único
            timestamp = node["updatedOnToOrder"]
            destacado = 1 if node["isPromoted"] else 0
            province_id = node["provinceId"]
            municipality_id = node["municipalityId"]
            vistas = node["viewCount"]

            phone = None
            whatsapp = 0
            if node["phoneInfo"] and node["phoneInfo"]["firstPhone"]:
                phone = node["phoneInfo"]["firstPhone"]["number"]
                whatsapp = 1 if node["phoneInfo"]["firstPhone"]["isWhatsapp"] else 0

            ubicacion = f"{provincias_dict.get(province_id, 'Desconocido')} - {municipios_dict.get(municipality_id, 'Desconocido')}"
            categoria = categorias_dict.get(node.get("categoryId"), "Desconocido")
            subcategoria = categorias_dict.get(node.get("subcategoryId"), None)

            # --- Chequeo de duplicados ---
            cur.execute("SELECT COUNT(*) FROM marketplace WHERE contexto = ?", (permalink,))
            existe = cur.fetchone()[0]

            # --- Filtrado por fecha ---
            if desde_fecha:
                try:
                    fecha_anuncio = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    fecha_limite = datetime.fromisoformat(desde_fecha)
                    if fecha_anuncio < fecha_limite:
                        skipped_count += 1
                        logging.warning(f"Anuncio anterior a fecha límite: {title} ({permalink}).")
                        print(f"[WARN] El anuncio '{title}' es anterior a {desde_fecha}, se omitió.")
                        continue
                except Exception as e:
                    logging.error(f"Error al parsear fecha: {timestamp} -> {e}")

            if existe > 0:
                skipped_count += 1
                logging.warning(f"Anuncio duplicado detectado: {title} ({permalink}). Sugerencia: ajustar fecha de inicio o detener en último registro.")
                print(f"[WARN] El anuncio '{title}' ya existe en la base de datos. Sugiere ajustar fecha de inicio o detener en el último registro.")
                continue  # saltar inserción

            # Insertar en usuarios
            cur.execute("INSERT OR IGNORE INTO usuarios (user_id, nombre, telefono) VALUES (?, ?, ?)", (user_id, None, phone))

            # Insertar en marketplace
            cur.execute("""INSERT INTO marketplace (user_id, categoria, subcategoria, nombre, precio, currency, ubicacion,
            telefono, whatsapp, imagen, destacado, vistas, timestamp, contexto)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, categoria, subcategoria, title, price, currency, ubicacion,
             phone, whatsapp, node["mainImage"]["gcsKey"], destacado, vistas, timestamp, permalink))
            ads_count += 1

        conn.commit()
        conn.close()
        logging.info(f"Scraping completado en {slug}: {ads_count} anuncios nuevos, {skipped_count} duplicados.")
        print(f"[INFO] Scraping completado en {slug}: {ads_count} anuncios nuevos, {skipped_count} duplicados.")

def cargar_categorias_html(soup):
    categorias_dict = {}
    for a in soup.select("a[href*='search?category=']"):
        slug = a["href"].split("category=")[-1].split("&")[0]
        titulo = a.get_text(strip=True)
        # Filtrar enlaces de paginación y textos inválidos
        if slug and titulo and "page=" not in slug and "cu=" not in slug and not titulo.isdigit():
            if titulo.lower() not in ["siguiente", "anterior"]:
                categorias_dict[slug] = titulo
    return categorias_dict

# --- CLI ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper Revolico con selección interactiva de categorías, control de duplicados y logging avanzado")
    parser.add_argument("--site", required=True, help="Nombre del sitio a scrapear (ej: revolico)")
    parser.add_argument("--sync", action="store_true", help="Solo sincronizar con la base original")
    parser.add_argument("--desde-fecha", help="Fecha mínima de anuncios en formato YYYY-MM-DD", required=False)
    args = parser.parse_args()

    init_db()

    if args.sync:
        scrape_revolico("", sync=True)
    else:
        if args.site.lower() == "revolico":
            url = "https://www.revolico.com/search?category=general"
            resp = requests.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
            data = json.loads(script_tag.string) if script_tag else {}

            municipios_dict, provincias_dict, categorias_dict = cargar_diccionarios(data)

            if not categorias_dict:
                print("[WARN] No se encontraron categorías en JSON. Intentando extraer del HTML...")
                categorias_dict = cargar_categorias_html(soup)

            if not categorias_dict:
                print("[ERROR] No se pudieron cargar categorías desde Revolico. Scraping abortado.")
                logging.error("No se pudieron cargar categorías desde Revolico. Scraping abortado.")
                exit(1)

            categorias_seleccionadas = seleccionar_categorias(categorias_dict)

            # Validar selección
            for slug in categorias_seleccionadas:
                if slug not in categorias_dict:
                    print(f"[ERROR] La categoría seleccionada '{slug}' no existe en el diccionario. Se omitirá.")
                    continue
                scrape_revolico(url, categorias_seleccionadas=[slug], desde_fecha=args.desde_fecha)

        else:
            url = f"https://www.revolico.com/search?category={args.site}"
            scrape_revolico(url, desde_fecha=args.desde_fecha)
