# ============================================================
# intent_semantic.py
# Motor semántico con corrector BK-tree + Levenshtein + Stanza
# ============================================================

import stanza
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
# Parth para Windows
# STANZA_DIR = r"c:\HellenData\StanfordNLP\stanza"

# Path para Linux
STANZA_DIR = r"/home/mnf/HellenData/StanfordNLP/stanza"

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
    download_method='reuse_resources'
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
# COPILOT-add: Nueva función para verificar palabras conocidas y evitar correcciones erróneas
# -----------------------------------------------------------
def is_known_word(word: str) -> bool:
    if not word:
        return False
    return not nlp.vocab[word].is_oov

# -----------------------------------------------------------
# Levenshtein simple (control de daño del corrector)
# -----------------------------------------------------------
def levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + cost
            ))
        prev = curr
    return prev[-1]

# -----------------------------------------------------------
# Mapa de verbos sin tilde → forma correcta con tilde
# (CAMBIO: corrección profesional de conjugaciones frecuentes)
# -----------------------------------------------------------
VERBOS_CON_TILDE = {
    "tendras": "tendrás",
    "tendra": "tendrá",
    "tendre": "tendré",
    "podras": "podrás",
    "podra": "podrá",
    "podre": "podré",
    "quisiera": "quisiera",
    "quisieras": "quisieras",
    "darias": "darías",
    "daria": "daría",
}

# -----------------------------------------------------------
# Corrector usando BK-tree (con capa de seguridad)
# -----------------------------------------------------------
def corregir_palabra(palabra: str) -> str:
    palabra_lower = palabra.lower()

    # CAMBIO: primero corregimos verbos comunes sin tilde
    if palabra_lower in VERBOS_CON_TILDE:
        return VERBOS_CON_TILDE[palabra_lower]

    if not palabra_lower.isalpha():
        return palabra

    if palabra_lower in PALABRAS_PROHIBIDAS:
        return palabra

    if palabra_lower in PALABRAS:
        return palabra

    if is_known_word(palabra_lower):
        # COPILOT-add: No corregir palabras válidas en spaCy para preservar significado
        return palabra

    candidatos = BK.buscar(palabra_lower, max_dist=2)
    if not candidatos:
        return palabra

    candidatos.sort(key=lambda x: x[0])
    return candidatos[0][1]

# CAMBIO: corrector “seguro” palabra a palabra, sin rollback global
# protege nombres propios, palabras de dominio, verbos con pronombres,
# palabras largas, palabras ya válidas y con tilde.
STOPWORDS = {
    "a","ante","bajo","cabe","con","contra","de","desde","durante",
    "en","entre","hacia","hasta","mediante","para","por","según",
    "sin","so","sobre","tras",
    "el","la","los","las","un","una","unos","unas",
    "y","o","u","pero","mas","sino",
    "que","como","cuando","donde","quien","cual","cuales"
}

PALABRAS_DOMINIO = {
    "venta","precio","contacto","telefono","número","ubicacion",
    "vendedor","comprador","whatsapp"
}

def correct_text(texto: str) -> str:
    tokens = TOKENIZER.findall(texto)
    corregidos = []

    for t in tokens:
        palabra = t

        # No es palabra → dejar igual
        if not palabra.isalpha():
            corregidos.append(palabra)
            continue

        pl = palabra.lower()

        # 1) STOPWORDS → nunca corregir
        if pl in STOPWORDS:
            corregidos.append(palabra)
            continue

        # 2) Palabras del dominio → nunca corregir
        if pl in PALABRAS_DOMINIO:
            corregidos.append(palabra)
            continue

        # 3) Palabras muy cortas → nunca corregir
        if len(pl) <= 3:
            corregidos.append(palabra)
            continue

        # 4) Verbos comunes sin tilde
        if pl in VERBOS_CON_TILDE:
            corregidos.append(VERBOS_CON_TILDE[pl])
            continue

        # 5) Palabras largas → BK-tree permitido
        if len(pl) >= 6:
            corregida = corregir_palabra(pl)
            if levenshtein_distance(pl, corregida) <= 2:
                corregidos.append(corregida)
            else:
                corregidos.append(palabra)
            continue

        # 6) Palabras medias (4–5 letras) → corrección muy conservadora
        corregida = corregir_palabra(pl)
        if levenshtein_distance(pl, corregida) == 1:
            corregidos.append(corregida)
        else:
            corregidos.append(palabra)

    # Reconstrucción
    out = []
    for i, t in enumerate(corregidos):
        if t.isalpha():
            if i > 0 and out and out[-1].isalpha():
                out.append(" ")
            out.append(t)
        else:
            out.append(t)

    return "".join(out)

# ============================================================
# 1. Extraer el verbo base (lemma) usando spaCy + Stanza
# ============================================================
# CAMBIO: usamos spaCy como primera pasada y Stanza como fallback
# analizando la frase completa; además, heurística de verbos con pronombres.
def obtener_verbo_base(texto: str):
    texto = normalize_text(texto)
    texto_corregido = correct_text(texto)

    print(f"[DEBUG] original:  {texto}")
    print(f"[DEBUG] corregido: {texto_corregido}")

    # spaCy sobre el texto corregido
    doc_spacy = nlp(texto_corregido)

    print("[DEBUG] tokens spaCy (Transformer):")
    for t in doc_spacy:
        print(f"  {t.text:<15} pos={t.pos_:6} lemma={t.lemma_}")

    verbos_encontrados = set()

    # Paso 1: primer verbo detectado por spaCy → Stanza para infinitivo
    for token in doc_spacy:
        if token.pos_ in ("VERB", "AUX"):
            verbo_spacy = token.text.lower()
            doc_stz = nlp_stanza(verbo_spacy)
            for sent in doc_stz.sentences:
                for word in sent.words:
                    if word.upos in ("VERB", "AUX"):
                        print(f"[DEBUG] Stanza lemma (spaCy→Stanza): {word.lemma}")
                        verbos_encontrados.add(word.lemma.lower())
            
            if not verbos_encontrados:
                verbos_encontrados.add(token.lemma_.lower())

    # Paso 2: Stanza analiza la frase completa (más robusto en español)
    doc_stanza_full = nlp_stanza(texto_corregido)
    for sent in doc_stanza_full.sentences:
        for w in sent.words:
            if w.upos in ("VERB", "AUX"):
                print(f"[DEBUG] Stanza lemma (full sentence): {w.lemma}")
                verbos_encontrados.add(w.lemma.lower())

    # Paso 3: heurística de verbos pegados a pronombres (darme, decirme, etc.)
    sufijos = ["me", "te", "se", "lo", "la", "los", "las"]
    for token in doc_spacy:
        palabra = token.text.lower()
        for sufijo in sufijos:
            if palabra.endswith(sufijo) and len(palabra) > len(sufijo) + 2:
                posible_verbo = palabra[:-len(sufijo)]
                print(f"[DEBUG] Verbo detectado por sufijo: {posible_verbo}")
                verbos_encontrados.add(posible_verbo)

    return list(verbos_encontrados)

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
    "querer": "COMPRA",  # quiero, queriendo

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
    
    "contactar": "CONTACTO",
    "comunicar": "CONTACTO",
    "facilitar": "CONTACTO",
    "agendar": "CONTACTO",
    "dar": "CONTACTO",  # "dame el contacto" → CONTACTO, no COMPRA

    "informar": "INFORMATIVA",
    "preguntar": "INFORMATIVA",
    "consultar": "INFORMATIVA",
    "poder": "INFORMATIVA",
    "saber": "INFORMATIVA",
    "existir": "INFORMATIVA",
    "haber": "INFORMATIVA",

    "notificar": "NOTIFICACION",
    "avisar": "NOTIFICACION",
    "registrar": "REGISTRO",
    "inscribir": "REGISTRO",
    "apuntar": "REGISTRO",
    "unir": "REGISTRO",
}

# ============================================================
# 3. Palabras clave por intención (NOUNS y contexto)
# ============================================================
# COPILOT-add: Diccionario de palabras clave (sustantivos, adjetivos)
# que refuerzan o corrigen la intención detectada por verbo.
# Estas palabras tienen MAYOR PRIORIDAD que el verbo en casos de conflicto.
PALABRAS_CLAVE_INTENCION = {
    # CONTACTO: palabras que indican búsqueda de contacto/información de vendedor
    "CONTACTO": {
        "contacto", "telefonico", "telefono", "numero", "celular", "whatsapp", 
        "email", "correo", "correos", "ubicacion", "ubicación", "direccion", "dirección", 
        "vendedor", "vendedores", "empresa", "empresas", "negocio", "negocios", 
        "tienda", "tiendas", "comercio", "comercios", "persona", "personas",
        "localizar", "ubicar", "localidad", "localidades", "zona", "zonas"
    },
    # INFORMATIVA: preguntas de información general
    "INFORMATIVA": {
        "precio", "precios", "especificacion", "especificación", "especificaciones",
        "caracteristica", "característica", "caracteristicas", "características",
        "disponible", "disponibilidad", "disponibles",
        "stock", "cantidad", "cantidades", "color", "colores", "tamaño", "tamaños",
        "marca", "marcas", "modelo", "modelos",
        "calidad", "garantia", "garantía", "envio", "envío", "tiempo", "costo", "costos"
    },
    # MENSAJERIA: envío, entrega, transporte
    "MENSAJERIA": {
        "envio", "envío", "envios", "envíos",
        "entrega", "entregas", "entregar", "entregable",
        "despacho", "despachos", "distribucion", "distribución", "distribuciones",
        "paquete", "paquetes", "caja", "cajas", "pallet", "pallets"
    },
    # COMPRA: búsqueda, adquisición, compra
    "COMPRA": {
        "compra", "compras", "comprador", "compradores",
        "busqueda", "búsqueda", "busquedas", "búsquedas",
        "buscar", "buscando", "necesidad", "necesidades"
    },
    # VENTA: oferta, venta, disponible para vender
    "VENTA": {
        "venta", "ventas", "vendedor", "vendedores",
        "oferta", "ofertas", "ofrecimiento", "ofrecimientos",
        "tengo", "traigo", "ofrezco", "ofresco"
    },
    # TRANSPORTE: transporte específico
    "TRANSPORTE": {
        "transporte", "transportes", "transportar",
        "traslado", "traslados", "mudanza", "mudanzas",
        "logistica", "logística", "flete", "fletes", "carga", "cargas"
    },
    # NOTIFICACION: alertas y avisos
    "NOTIFICACION": {
        "aviso", "avisos", "notificacion", "notificación", "notificaciones",
        "alerta", "alertas", "suscripcion", "suscripción"
    },
    # REGISTRO: registro de usuarios, vendedores o compradores
    "REGISTRO": {
        "registro", "registrame", "regístrame", "registrarme", "inscripcion", "inscripción",
        "inscribirme", "alta", "unirme", "cuenta", "perfil", "vendedor", "comprador"
    }
}

# ============================================================
# 3. Detector semántico de intención (MEJORADO)
# ============================================================
# COPILOT-add: Sistema de detección de intención que considera:
# 1. Palabras clave contextuales (sustantivos, adjetivos)
# 2. Verbo base (fallback)
# 3. Lógica de refinamiento para casos ambiguos
#
# PROBLEMA ANTERIOR:
#   "dame el contacto de un vendedor" → solo ve "dame" → COMPRA (INCORRECTO)
#
# SOLUCIÓN:
#   Analiza sustantivos: "contacto", "vendedor", "ubicacion" → CONTACTO ✓
#
def detectar_intencion_semantica(mensaje: str):
    mensaje_lower = mensaje.lower()
    
    # Paso 1: Extraer TODOS los sustantivos y palabras significativas
    texto_normalizado = normalize_text(mensaje_lower)
    texto_corregido = correct_text(texto_normalizado)
    doc_spacy = nlp(texto_corregido)
    
    # Recopilar todos los NOUNs y ADJs para análisis de contexto
    # COPILOT-add: Normalizar palabras para comparación (sin tilde)
    palabras_contextuales = set()
    palabras_debug = []
    
    for token in doc_spacy:
        if token.pos_ in ("NOUN", "ADJ", "PROPN"):
            # Normalizar: remover tildes para comparación
            lemma_limpio = unicodedata.normalize('NFD', token.lemma_.lower())
            lemma_sin_tilde = ''.join(c for c in lemma_limpio if unicodedata.category(c) != 'Mn')
            
            palabras_contextuales.add(lemma_sin_tilde)
            palabras_debug.append(f"{token.text}({token.pos_}) → lemma={token.lemma_} → limpio={lemma_sin_tilde}")
    
    print(f"[DEBUG] Palabras contextuales extraidas:")
    for w in palabras_debug:
        print(f"  {w}")
    print(f"[DEBUG] Set final: {palabras_contextuales}")
    
    # Paso 2: Buscar coincidencias con palabras clave por intención
    PRIORIDADES = ["REGISTRO", "CONTACTO", "MENSAJERIA", "VENTA", "COMPRA", "INFORMATIVA", "NOTIFICACION", "OTRA"]
    intenciones_detectadas = []
    
    for intencion in PRIORIDADES:
        if intencion in PALABRAS_CLAVE_INTENCION:
            palabras_clave = PALABRAS_CLAVE_INTENCION[intencion]
            
            # Normalizar palabras clave también para comparación sin tilde
            palabras_clave_normalizadas = set()
            for pc in palabras_clave:
                pc_limpio = unicodedata.normalize('NFD', pc.lower())
                pc_sin_tilde = ''.join(c for c in pc_limpio if unicodedata.category(c) != 'Mn')
                palabras_clave_normalizadas.add(pc_sin_tilde)
            
            coincidencias = palabras_contextuales & palabras_clave_normalizadas
            if coincidencias:  # Intersección no vacía
                print(f"[DEBUG] ✅ Intención detectada por palabras clave: {intencion}")
                print(f"[DEBUG] Coincidencias encontradas: {coincidencias}")
                if intencion not in intenciones_detectadas:
                    intenciones_detectadas.append(intencion)
    
    if not intenciones_detectadas:
        print(f"[DEBUG] No se encontraron palabras clave, intentando verbo base...")
    
    # Paso 3: Fallback a verbo base
    verbos = obtener_verbo_base(mensaje_lower)
    es_pregunta = "?" in mensaje or mensaje_lower.startswith(("que", "como", "donde", "cuando", "quien", "cual", "tendras", "tienes", "vendes", "hay"))

    if verbos:
        for verbo in verbos:
            intencion_verbo = VER_INTENT.get(verbo)
            if intencion_verbo:
                # Regla especial: si pregunta "¿vendes X?" o "¿tienes X?", es COMPRA, no VENTA
                if verbo in ["vender", "tener", "disponer", "haber", "existir"] and es_pregunta:
                    if "COMPRA" not in intenciones_detectadas:
                        intenciones_detectadas.append("COMPRA")
                    if "INFORMATIVA" not in intenciones_detectadas:
                        intenciones_detectadas.append("INFORMATIVA")
                    # Evitar que "vender" dispare VENTA si es una pregunta del comprador
                    if "VENTA" in intenciones_detectadas and verbo == "vender":
                        intenciones_detectadas.remove("VENTA")
                elif intencion_verbo not in intenciones_detectadas:
                    print(f"[DEBUG] Intención por verbo: {intencion_verbo} (verbo: {verbo})")
                    intenciones_detectadas.append(intencion_verbo)

    # Refinamiento final: si hay COMPRA y es pregunta, suele ser INFORMATIVA también
    if "COMPRA" in intenciones_detectadas and es_pregunta and "INFORMATIVA" not in intenciones_detectadas:
        intenciones_detectadas.append("INFORMATIVA")

    # CURSOR-add: "cómo llego al vendedor X" es navegación, no pedido de teléfono (CONTACTO)
    msg_nav = normalize_text(mensaje_lower)
    patrones_navegacion = [
        r"\bcomo llego\b", r"\bcomo llegar\b", r"\bllegar al\b", r"\bllegar a\b",
        r"\bindicaciones\b", r"\bruta\b", r"\btrazar\b", r"\bdonde queda\b",
    ]
    if any(re.search(p, msg_nav) for p in patrones_navegacion):
        if "CONTACTO" in intenciones_detectadas:
            intenciones_detectadas.remove("CONTACTO")
            print("[DEBUG] CURSOR: CONTACTO removido — frase de navegación detectada", flush=True)
        if "INFORMATIVA" not in intenciones_detectadas:
            intenciones_detectadas.append("INFORMATIVA")

    if not intenciones_detectadas:
        print(f"[DEBUG] No se detectó intención, retornando ['OTRA']")
        return ["OTRA"]

    return intenciones_detectadas
