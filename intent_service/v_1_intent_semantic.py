# ============================================================
# intent_semantic.py
# Motor semántico con corrector BK-tree + Levenshtein
# ============================================================

import stanza
# from stanza.models.common import download_method
import unicodedata
import os
import re
from app.core.pipeline.nlp_loader import nlp
from app.core.pipeline.bk_tree import BKTree

# -----------------------------------------------------------
# Cargar diccionario español extendido
# -----------------------------------------------------------
BASE_DIR = os.path.dirname(__file__)
DICCIONARIO_FILE = os.path.join(BASE_DIR, "custom_dict")
STANZA_DIR = r"c:\HellenData\StanfordNLP\stanza"

if not os.path.exists(DICCIONARIO_FILE):
    raise FileNotFoundError("custom_dict no encontrado")

with open(DICCIONARIO_FILE, "r", encoding="utf-8") as f:
    PALABRAS = [p.strip().lower() for p in f if p.strip()]

print("[INFO] Construyendo BK-tree…")
BK = BKTree(PALABRAS[0])
for palabra in PALABRAS[1:]:
    BK.insertar(palabra)

nlp_stanza = stanza.Pipeline(
    lang='es',
    dir=STANZA_DIR,
    processors='tokenize,pos,lemma',
    package='ancora',
    use_gpu=False,
    download_method='reuse_resources'  # <- evita descargas repetidas
)

print("[DEBUG] PALABRAS cargadas:", len(PALABRAS))
print("[DEBUG] Primeras 20:", PALABRAS[:20])
print("[INFO] BK-tree cargado con éxito.")

# -----------------------------------------------------------
# Blacklist
# -----------------------------------------------------------
PROHIBIDAS_FILE = "words_black_list"
PALABRAS_PROHIBIDAS = set()

if os.path.exists(PROHIBIDAS_FILE):
    with open(PROHIBIDAS_FILE, "r", encoding="utf-8") as f:
        for linea in f:
            palabra = linea.strip().lower()
            if palabra:
                PALABRAS_PROHIBIDAS.add(palabra)

# ----------------------------------------------------------
# TOKENIZER
# ----------------------------------------------------------
TOKENIZER = re.compile(r"\w+|[^\w\s]", re.UNICODE)

# -----------------------------------------------------------
# Normaliza Unicode
# -----------------------------------------------------------
def normalize_text(t: str) -> str:
    return unicodedata.normalize("NFC", t)

# -----------------------------------------------------------
# Palabra válida en el vocabulario de spaCy
# -----------------------------------------------------------
def is_known_word(word: str) -> bool:
    if not word:
        return False
    return not nlp.vocab[word].is_oov

# -----------------------------------------------------------
# Corrector usando BK-tree
# -----------------------------------------------------------
def corregir_palabra(palabra: str) -> str:
    palabra_lower = palabra.lower()

    if not palabra_lower.isalpha():
        return palabra

    if palabra_lower in PALABRAS_PROHIBIDAS:
        return palabra

    if palabra_lower in PALABRAS:
        return palabra

    if is_known_word(palabra_lower):
        return palabra

    # Buscar candidatos en BK-tree
    candidatos = BK.buscar(palabra_lower, max_dist=2)
    if not candidatos:
        return palabra

    candidatos.sort(key=lambda x: x[0])
    return candidatos[0][1]

def correct_text(texto: str) -> str:
    tokens = TOKENIZER.findall(texto)
    corregidos = []

    for t in tokens:
        if t.isalpha():
            corregidos.append(corregir_palabra(t))
        else:
            corregidos.append(t)

    # reconstruir con espacios solo entre palabras
    resultado = []
    for i, t in enumerate(corregidos):
        if t.isalpha():
            if i > 0 and resultado and resultado[-1].isalpha():
                resultado.append(" ")
            resultado.append(t)
        else:
            resultado.append(t)

    return "".join(resultado)

# ============================================================
# 1. Extraer el verbo base (lemma)
# ============================================================
def obtener_verbo_base(texto: str):
    texto = normalize_text(texto)
    texto_corregido = correct_text(texto)

    print(f"[DEBUG] original:  {texto}")
    print(f"[DEBUG] corregido: {texto_corregido}")

    # Paso 1: spaCy para análisis sintáctico
    doc = nlp(texto_corregido)

    print("[DEBUG] tokens spaCy (Transformer):")
    for t in doc:
        print(f"  {t.text:<15} pos={t.pos_:<6} lemma={t.lemma_}")

    # Paso 2: tomar el primer verbo detectado por spaCy
    for token in doc:
        if token.pos_ in ("VERB", "AUX"):
            verbo_spacy = token.text.lower()

            # Paso 3: pasar ese verbo a Stanza para obtener el infinitivo
            doc_stanza = nlp_stanza(verbo_spacy)
            for sent in doc_stanza.sentences:
                for word in sent.words:
                    if word.upos in ("VERB", "AUX"):
                        print(f"[DEBUG] Stanza lemma: {word.lemma}")
                        return word.lemma.lower()

            # Fallback: si Stanza no devuelve nada, usar el lema de spaCy
            return token.lemma_.lower()

    return None

def v_1_obtener_verbo_base(texto: str):
    texto = normalize_text(texto)
    texto_corregido = correct_text(texto)

    print(f"[DEBUG] original:  {texto}")
    print(f"[DEBUG] corregido: {texto_corregido}")

    doc = nlp(texto_corregido)

    print("[DEBUG] tokens spaCy (Transformer):")
    for t in doc:
        print(f"  {t.text:<15} pos={t.pos_:<6} lemma={t.lemma_}")

    for token in doc:
        if token.pos_ in ("VERB", "AUX"):
            return token.lemma_.lower()

    return None

# ============================================================
# 2. Diccionario semántico VERBO → INTENCIÓN
# ============================================================
VER_INTENT = {
    "tener": "COMPRA",
    "buscar": "COMPRA",
    "comprar": "COMPRA",
    "necesitar": "COMPRA",
    "adquirir": "COMPRA",
    "pedir": "COMPRA",
    "solicitar": "COMPRA",

    "vender": "VENTA",
    "ofrecer": "VENTA",
    "disponer": "VENTA",
    "ofertar": "VENTA",

    "enviar": "MENSAJERIA",
    "mandar": "MENSAJERIA",
    "entregar": "MENSAJERIA",

    "transportar": "TRANSPORTE",
    "llevar": "TRANSPORTE",
    "mover": "TRANSPORTE",

    "informar": "INFORMATIVA",
    "preguntar": "INFORMATIVA",
    "consultar": "INFORMATIVA",
    "saber": "INFORMATIVA",

    "notificar": "NOTIFICACION",
    "avisar": "NOTIFICACION",
}

# ============================================================
# 3. Detector semántico de intención
# ============================================================
def detectar_intencion_semantica(mensaje: str):
    verbo = obtener_verbo_base(mensaje)
    if not verbo:
        return None
    return VER_INTENT.get(verbo, "ACLARAR_INTENCION")
