import stanza
import os
import shutil

# Carpeta destino fija en tu proyecto
STANZA_DIR = r"c:\HellenData\StanfordNLP\stanza"
ES_MODEL_DIR = os.path.join(STANZA_DIR, "es")

# Carpeta de caché original
CACHE_DIR = r"c:\HellenData\StanfordNLP\stanza\Cache\1.11.0\resources\es"

# 1. Si no existe en el proyecto pero sí en la caché → copiar
if not os.path.exists(ES_MODEL_DIR) and os.path.exists(CACHE_DIR):
    print("[INFO] Copiando modelo de español desde la caché al proyecto...")
    shutil.copytree(CACHE_DIR, ES_MODEL_DIR)

# 2. Si aún no existe en el proyecto → descargar directamente allí
if not os.path.exists(ES_MODEL_DIR):
    print("[INFO] Descargando modelo de español en", STANZA_DIR)
    stanza.download('es', dir=STANZA_DIR)

# 3. Inicializar el pipeline desde la carpeta fija del proyecto
print("[INFO] Inicializando pipeline de Stanza desde", STANZA_DIR)
nlp_stanza = stanza.Pipeline(
    lang='es',
    dir=STANZA_DIR,
    processors='tokenize,pos,lemma',
    use_gpu=False
)

# Ejemplo de uso
doc = nlp_stanza("Hola, tendrás arroz?")
for sent in doc.sentences:
    for word in sent.words:
        print(f"{word.text:<10} pos={word.upos:<6} lemma={word.lemma}")
