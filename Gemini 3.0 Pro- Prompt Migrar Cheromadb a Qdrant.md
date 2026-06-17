# CONTEXTO DEL SISTEMA: HellenCommerce 2.0.1
Estoy trabajando sobre el componente "Orchestrator Core", el cual está diseñado y operando como una librería interna (NO un microservicio). Esta librería coordina todo el flujo de peticiones desde FastAPI hacia los microservicios especializados bajo el siguiente flujo secuencial:
1. Recibe petición desde FastAPI WebSocket.
2. Detecta intención(es) vía `intent_service`.
3. Genera prompts personalizados vía `worker_service`.
4. Despacha en paralelo a servicios especializados (fan-out).
5. Unifica respuestas vía `mistral_service`.
6. Persiste contexto en SQLite/ChromaDB. <--- (AQUÍ REQUERIMOS LA MODIFICACIÓN EXCLUSIVA PARA CHROMADB).
7. Retorna respuesta al cliente vía WebSocket.

# OBJETIVO DEL PROMPT
Actúa como un Ingeniero de Software Senior experto en Python e Infraestructura de IA. Necesito modificar EXCLUSIVAMENTE los módulos, clases o funciones responsables del componente de vectores (ChromaDB) en el **Paso 6 (Persiste contexto en SQLite/ChromaDB)** de mi Orquestador y las librerías locales que lo soportan. El objetivo es introducir soporte para **Qdrant Cloud (Online en Google Cloud)** sin eliminar el soporte actual de **ChromaDB (Local como microservicio)**.

Para mantener la integridad absoluta de HellenCommerce, NO debes alterar la lógica de los pasos 1, 2, 3, 4, 5 ni 7, ni cambiar la firma de las funciones que invoca el orquestador core. Las firmas de las funciones deben seguir aceptando y retornando exactamente los mismos tipos de datos.

# REQUERIMIENTOS ESTRICTOS DE CÓDIGO

1. **Protección de SQLite (No tocar):**
   La base de datos relacional local SQLite debe mantenerse intacta y seguir operando localmente de la misma manera que lo hace hoy. La migración y la lógica híbrida afectan únicamente a la base de datos vectorial (ChromaDB / Qdrant).

2. **Conmutación por Variable de Entorno:**
   El sistema debe evaluar en caliente la variable `VECTOR_DB_TYPE = os.getenv("VECTOR_DB_TYPE", "chromadb")`.
   - Si es `"chromadb"`, ejecutará las llamadas HTTP existentes hacia el microservicio local de ChromaDB.
   - Si es `"qdrant"`, ejecutará las llamadas equivalentes hacia Qdrant Cloud usando las variables `QDRANT_URL` y `QDRANT_API_KEY`.

3. **Generación de Embeddings Online (Hugging Face):**
   Elimina por completo el uso de la librería local `sentence-transformers` para liberar memoria RAM. El sistema ahora debe calcular los embeddings de forma remota utilizando el SDK oficial `huggingface_hub`. 
   - Usa el modelo `"sentence-transformers/all-MiniLM-L6-v2"` a través del pipeline `hf_client.feature_extraction(text, model)`.
   - Asegúrate de que las funciones de persistencia y búsqueda invoquen esta API online para obtener el vector numérico de 384 dimensiones antes de guardarlo o consultarlo en la base de datos vectorial activa.

4. **Integridad de las Funciones del Paso 6 (ChromaDB vs Qdrant Cloud):**
   Modifica las funciones de persistencia y recuperación semántica manteniendo exactamente sus nombres y parámetros de entrada actuales. En la sección de Qdrant (`qdrant-client`), debes asegurar:
   - **Inicialización/Asegurar Colección:** Crear la colección si no existe en la nube usando la métrica `Distance.COSINE` y configurando el tamaño estricto en 384 dimensiones.
   - **Guardar Contexto (Persistencia):** Mapear el identificador del usuario (`user_id`), las intenciones detectadas en el paso 2 y el texto unificado dentro del objeto `payload` de Qdrant.
   - **Recuperar Contexto:** Aplicar un filtro de metadatos estricto por `user_id` en Qdrant para garantizar el aislamiento de datos (un cliente de la tienda no debe leer el contexto conversacional de otro). Debe retornar el texto limpio estructurado en el mismo formato exacto que ChromaDB para que los pasos posteriores consuman el RAG de forma idéntica.

# RESULTADO ESPERADO
Entrégame el código limpio, optimizado y puramente en Python correspondiente al archivo de la capa de persistencia (el cual guardaré manualmente en mi directorio local `c:\HellenCommerce\`). Usa los SDKs oficiales ligeros `qdrant-client` y `huggingface_hub`, garantizando que el archivo esté completamente libre de dependencias pesadas locales de Deep Learning como PyTorch o Transformers locales.
