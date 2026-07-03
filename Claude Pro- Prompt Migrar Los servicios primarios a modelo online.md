# SYSTEM ROLE
Actúas como un Ingeniero de Software Principal y Arquitecto de Infraestructura de IA Cloud Native. Tu especialidad es migrar sistemas de producción híbridos (modelos locales GGUF y APIs comerciales pagas) hacia arquitecturas unificadas en la nube a coste cero, implementando patrones de diseño altamente tolerantes a fallos (Fallback / Dual-Mode) sin romper la compatibilidad hacia atrás.

# CONTEXTO DEL SISTEMA: HellenCommerce (Continuación de Servicios Primarios)
En la raíz de mi proyecto `c:\HellenCommerce\`, cuento con tres servicios primarios críticos administrados por el Orquestador. Actualmente están configurados con una mezcla de microservicios locales GGUF y llamadas directas a APIs externas de pago:

1. **`intent_service`**: Detecta intenciones consumiendo de forma local el modelo `mistral-7b-instruct-v0.2.Q4_K_M.gguf`.
2. **`loggin_service`**: Maneja el flujo con un modelo comercial externo configurado de la siguiente manera:
   `EXTERNAL_LLM_URL = os.getenv("EXTERNAL_LLM_URL", "https://api.anthropic.com/v1/messages")`
   `EXTERNAL_LLM_KEY = os.getenv("EXTERNAL_LLM_KEY", "")`
   `EXTERNAL_LLM_MODEL = os.getenv("EXTERNAL_LLM_MODEL", "claude-3-5-sonnet-20241022")`
   *Restricción Crítica:* No dispongo de un Token / API Key de Anthropic comercial de pago activo.
3. **`mistral_service`**: Unifica y procesa respuestas consumiendo localmente el modelo `qwen2.5-3b-instruct-q4_k_m.gguf`.

# OBJETIVO DEL PROMPT
Refactorizar y modificar EXCLUSIVAMENTE estos tres servicios primarios para que sean refactorizados o migren a sus versiones **Online Gratuitas** (Serverless). Al igual que hicimos con los servicios secundarios, el sistema debe quedar configurado en un formato dual utilizando condicionales `if/else` controlados por una variable de entorno (`LLM_MODE = os.getenv("LLM_MODE", "online")`), permitiendo alternar entre el flujo local heredado y el nuevo motor serverless en la nube sin alterar las firmas, nombres ni datos de retorno esperados por el Orquestador central.

# REQUERIMIENTOS ESTRICTOS DE REFACTORIZACIÓN
Procesa las siguientes directrices técnicas delimitadas en etiquetas XML para construir tu respuesta:

<requerimiento_1_intent_service_online>
Para el módulo `intent_service`, cuando `LLM_MODE == "online"`:
- Elimina la petición POST local hacia el microservicio GGUF.
- Implementa el SDK oficial `from huggingface_hub import InferenceClient` inicializado de forma segura con `os.getenv("HF_TOKEN")`.
- Redirecciona las solicitudes de inferencia al repositorio oficial online gratuito: `"mistralai/Mistral-7B-Instruct-v0.2"`.
</requerimiento_1_intent_service_online>

<requerimiento_2_loggin_service_free_fallback>
Para el módulo `loggin_service`, dado que NO se dispone de un token comercial de Anthropic (`EXTERNAL_LLM_KEY` estará vacío), cuando `LLM_MODE == "online"` el sistema debe realizar un Fallback táctico a coste cero:
- En lugar de colapsar o intentar golpear la API de Anthropic sin token, redirige el flujo de forma transparente utilizando el cliente de Hugging Face (`huggingface_hub`).
- Consume un modelo gratuito equivalente de altas prestaciones en la nube de Hugging Face como `"Qwen/Qwen2.5-72B-Instruct"` (o similar de alta capacidad lógica). El cambio de modelo debe ser imperceptible para el Orquestador, devolviendo exactamente el mismo formato de texto limpio.
</requerimiento_2_loggin_service_free_fallback>

<requerimiento_3_mistral_service_online>
Para el módulo `mistral_service` (que localmente levantaba un modelo Qwen de 3B parámetros), cuando `LLM_MODE == "online"`:
- Conéctalo a la API Serverless gratuita de Hugging Face usando `InferenceClient`.
- Apunta las solicitudes de inferencia al modelo online oficial correspondiente de su misma familia en la nube: `"Qwen/Qwen2.5-7B-Instruct"` (o superior de la misma rama).
</requerimiento_3_mistral_service_online>

<requerimiento_4_conmutacion_dual>
En los tres archivos correspondientes, estructura el código con un bloque condicional limpio:
- `if LLM_MODE == "local":` -> Ejecuta el código HTTP/Microservicio antiguo original (GGUF o endpoint de Anthropic).
- `else:` -> Ejecuta la nueva lógica optimizada mediante `huggingface_hub.InferenceClient` explicada en los puntos anteriores.
Asegúrate de mantener intactas las variables de los prompts estructurados de entrada y el manejo de excepciones de red.
</requerimiento_4_conmutacion_dual>

# RESULTADO ESPERADO
Entrégame las refactorizaciones de código estructuradas y limpias en Python para cada uno de estos tres servicios primarios (`intent_service`, `loggin_service`, `mistral_service`) listos para ser guardados en la ruta `c:\HellenCommerce\`. Garantiza que estén libres de librerías locales de Deep Learning y optimizados para entornos de producción concurrentes asíncronos (`async/await`).
