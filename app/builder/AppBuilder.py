# app/builder/AppBuilder.py

from app.adapters.rag.ChromaAdapter import ChromaAdapter
from app.adapters.rag.EmbeddingAdapter import EmbeddingAdapter
from app.adapters.rag.QueryAdapter import QueryAdapter

from app.context.ContextManager import ContextManager

from app.core.pipeline.RoleDetector import RoleDetector
from app.core.pipeline.InfoExtractor import InfoExtractor
from app.core.pipeline.BusinessLogic import BusinessLogic
from app.core.pipeline.PromptBuilder import PromptBuilder

from app.core.builder.IARequestBuilder import IARequestBuilder
from app.core.builder.IARequestDirector import IARequestDirector

from app.adapters.db.SQLiteAdapter import SQLiteAdapter
from app.adapters.mqtt.MQTTAdapter import MQTTAdapter
from app.core.notifications.NotificationManager import NotificationManager
from app.core.pipeline.map_logic import MapLogic
import os


class AppBuilder:
    """
    Construye todos los componentes del sistema IA-Broker.
    Este builder se ejecuta UNA VEZ por worker de Gunicorn.
    """

    def __init__(self):
        # ---------------------------------------------------------
        # 1. Construir Base de datos
        # ---------------------------------------------------------
        self.db = SQLiteAdapter()

        # Aplicar PRAGMAs usando una conexión temporal
        try:
            conn = self.db._get_conn()
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
        finally:
            conn.close()

        # ---------------------------------------------------------
        # 2. Construir Embeddings (global, seguro)
        # ---------------------------------------------------------
        self.embedder = EmbeddingAdapter()

        # ---------------------------------------------------------
        # 3. Construir Context Manager
        # ---------------------------------------------------------
        self.ctx = ContextManager(
            db=self.db,
            rag=self.get_rag,                     # fábrica        
            embedder=self.embedder,
            query_adapter=self.get_query_adapter  # fábrica
        )

        # ---------------------------------------------------------
        # 4. Construir Detectar Rol
        # ---------------------------------------------------------
        self.role_detector = RoleDetector()

        # ---------------------------------------------------------
        # 5. Construir Extraer Informacion de la DB
        # ---------------------------------------------------------
        self.extractor = InfoExtractor()

        # ---------------------------------------------------------
        # 6. Construir NOtificador Push
        # ---------------------------------------------------------
        self.MQTT_HOST = os.getenv("MQTT_HOST")
        self.MQTT_PORT = os.getenv("MQTT_PORT")

        self.mqtt = MQTTAdapter(host=self.MQTT_HOST, port=self.MQTT_PORT)

        self.notification_manager = NotificationManager(
            db=self.db,
            mqtt=self.mqtt,
            interval=10
        )

        # ---------------------------------------------------------
        # 7. Construir Mapas
        # ---------------------------------------------------------
        self.map_logic = MapLogic()

        # ---------------------------------------------------------
        # 8. Construir Logoca del Negocio
        # ---------------------------------------------------------
        self.business_logic = BusinessLogic(
            db=self.db,
            extractor=self.extractor,
            rag_factory=self.get_rag,                    # fábrica
            embedder=self.embedder,
            query_adapter=self.get_query_adapter(), # fábrica
            mqtt=self.mqtt,
            map_logic=self.map_logic
        )

        # ---------------------------------------------------------
        # 9. Construir Prompt
        # ---------------------------------------------------------
        self.prompt_builder = PromptBuilder()

        # ---------------------------------------------------------
        # 10. Inicializar en None Modelo de lenguaje (inyectado luego)
        # ---------------------------------------------------------
        self.model = None

        # ---------------------------------------------------------
        # 11. Construir IARequestBuilder 
        # ---------------------------------------------------------
        self.ia_builder = IARequestBuilder(
            db=self.db,                          # Pasar SB Construida en el Paso 1
            context_manager=self.ctx,            # Pasar Context_Manager Construida en el Paso 3
            role_detector=self.role_detector,    # Pasar Detector de Roles Construida en el Paso 4
            business_logic=self.business_logic,  # Pasar Logica del Negocio Construida en el Paso 8
            prompt_builder=self.prompt_builder,  # Pasar Constructor de Prompt Construida en el Paso 9
            model=self.model,
            rag_factory=self.get_rag,            # Pasar RAG Construido con ChromaAdapter (DB Semantica)
            embedding_adapter=self.embedder      # Pasar embedding Construidos en el Paso 2
        )

        # ---------------------------------------------------------
        # 12. Construir Director desde IARequestDirector
        # Costructor pasa informacion al Director para ser procesada
        # o Director recibe la infomacion que el constructor le trajo
        # ---------------------------------------------------------
        self.director = IARequestDirector(self.ia_builder)

    # ---------------------------------------------------------
    # Fábricas de RAG y QueryAdapter (instancias nuevas por request)
    # ---------------------------------------------------------
    def get_rag(self):  
        return ChromaAdapter()

    def get_query_adapter(self):
        return QueryAdapter(
            rag=self.get_rag(),
            embedder=self.embedder
        )

    # ---------------------------------------------------------
    # Cargar embeddings en startup_event
    # ---------------------------------------------------------
    def load_embeddings(self):
        print(">>> Cargando modelo MiniLM...")
        self.embedder.load()
        print(">>> Embeddings cargados correctamente.")

    # ---------------------------------------------------------
    # Exponer director COnstruido en el paso 12
    # ---------------------------------------------------------
    def get_director(self):
        return self.director
