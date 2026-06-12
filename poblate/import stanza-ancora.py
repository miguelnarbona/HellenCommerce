
import os, shutil
import stanza

# Descarga el paquete ancora en la caché
stanza.download("es", package="ancora")

STANZA_DIR = r"c:\HellenData\StanfordNLP\stanza"
CACHE_DIR = r"c:\Users\Miguel Narbona\AppData\Local\stanfordnlp\stanza\resources\es"
PROJECT_DIR = r"c:\HellenData\StanfordNLP\stanza\es"

# Crear destino si no existe
os.makedirs(PROJECT_DIR, exist_ok=True)

# Copiar solo los ficheros que contengan 'ancora' en el nombre
for root, dirs, files in os.walk(CACHE_DIR):
    for file in files:
        if "ancora" in file:
            src_path = os.path.join(root, file)
            # reconstruir la misma estructura de carpetas en el proyecto
            rel_path = os.path.relpath(root, CACHE_DIR)
            dest_dir = os.path.join(PROJECT_DIR, rel_path)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, file)
            print(f"[INFO] Copiando {src_path} -> {dest_path}")
            shutil.copy2(src_path, dest_path)
