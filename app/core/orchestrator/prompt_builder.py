"""
HellenCommerce 2.0.1 - Prompt Builder Service

Componente del orquestador para construcción de prompts especializados.

Flujo por intención:
  1. Carga la plantilla .txt correcta según la intención detectada
     (con inversión de roles: COMPRA → vendedor, VENTA → comprador).
  2. Consulta Qdrant para recuperar recuerdos conversacionales del usuario
     filtrados estrictamente por user_id.
  3. Ensambla el prompt final completo listo para enviarse al modelo en línea:
        [system_template del .txt]
        HISTORIAL CONVERSACIONAL: {contexto_previo}
        RECUERDOS RELEVANTES (RAG/Qdrant): {rag_snippets}
        INTENCIÓN DETECTADA: {intent}
        MENSAJE DEL USUARIO: {message}
  4. Para multi-intención (>= 2 intenciones) usa prompt_multi_intencion.txt
     y retorna UN SOLO prompt con clave "MULTI" para que mistral_service unifique.
  5. Enriquecimiento opcional via worker_service (/enrich_prompt) con datos de BD.
  6. Fallback real: si el worker_service no está disponible, usa el .txt como base
     (nunca strings triviales sin instrucciones para el modelo).
"""

import os
import httpx
from pathlib import Path
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# Mapa intención → fichero de prompt  (con inversión de roles correcta)
# ---------------------------------------------------------------------------
# La IA asume el ROLE CONTRARIO o complementario al del usuario:
#   Usuario COMPRA  → IA es VENDEDOR  (broker_prompt_vendedor.txt)
#   Usuario VENDE   → IA es COMPRADOR (broker_prompt_comprador.txt)
#   Resto           → IA asume el role especializado del prompt
_INTENT_TO_FILE: Dict[str, str] = {
    "COMPRA":       "broker_prompt_vendedor.txt",   # IA actúa como vendedor
    "VENTA":        "broker_prompt_comprador.txt",  # IA actúa como comprador/evaluador
    "INFORMATIVA":  "prompt_informativo.txt",
    "NOTIFICACION": "prompt_notificacion.txt",
    "NEGOCIO":      "prompt_negocio.txt",
    "CONTACTO":     "prompt_contacto.txt",
    "MENSAJERIA":   "prompt_mensajeria.txt",
    "TRANSPORTE":   "prompt_transporte.txt",
    "RUTA":         "prompt_ruta.txt",
    "REGISTRO":     "prompt_registro.txt",
    "SERVICIO":     "prompt_servicio.txt",
    "SALUDO":       "prompt_saludo.txt",
    "DESPEDIDA":    "prompt_saludo.txt",   # comparte plantilla con saludo
    "OTRA":         "prompt_otra.txt",
}

_MULTI_INTENT_FILE = "prompt_multi_intencion.txt"

# Umbral: con >= N intenciones se activa el modo multi-intención
_MULTI_INTENT_THRESHOLD = 2


class PromptBuilderService:
    """
    Construye prompts especializados completos para cada intención detectada.

    Para intención única:
        Lee el .txt correspondiente → consulta Qdrant → ensambla prompt.
    Para multi-intención (>= _MULTI_INTENT_THRESHOLD):
        Lee prompt_multi_intencion.txt → rellena variables → retorna {"MULTI": prompt}.
    """

    def __init__(self, service_url: str = None, base_prompts_path: str = None):
        self.service_url = self._normalize_service_url(
            service_url or os.getenv("WORKER_SERVICE_URL", "http://bunker_worker_service:9000")
        )
        from app.utils.paths import hc_path
        self.base_prompts_path = Path(base_prompts_path or hc_path("app/prompts"))

        # Adaptadores RAG — inicialización lazy para no bloquear el arranque
        self._rag = None
        self._embedder = None

    # -----------------------------------------------------------------------
    # Normalización de URL del worker_service
    # -----------------------------------------------------------------------
    @staticmethod
    def _normalize_service_url(url: str | None) -> str:
        if not url:
            return "http://bunker_worker_service:9000"
        value = url.strip()
        alias_map = {
            "http://127.0.0.1:9000":             "http://bunker_worker_service:9000",
            "http://worker_service:9000":         "http://bunker_worker_service:9000",
            "http://bunker_worker_service:9000":  "http://bunker_worker_service:9000",
        }
        return alias_map.get(value, value)

    # -----------------------------------------------------------------------
    # Normalización del contexto previo → siempre lista de strings
    # -----------------------------------------------------------------------
    @staticmethod
    def _normalize_contexto(contexto: Any) -> List[str]:
        """Convierte cualquier forma de contexto a una lista de líneas de texto."""
        if contexto is None:
            return []
        if isinstance(contexto, list):
            return [str(l) for l in contexto if l]
        if isinstance(contexto, dict):
            lines = contexto.get("history", contexto.get("raw", []))
            return [str(l) for l in lines if l]
        return [str(contexto)]

    # -----------------------------------------------------------------------
    # Inicialización lazy de los adaptadores RAG (Qdrant / ChromaDB)
    # -----------------------------------------------------------------------
    def _ensure_rag(self):
        """Inicializa RAG y embedder la primera vez que se necesitan."""
        if self._rag is None or self._embedder is None:
            try:
                from app.adapters.rag.ChromaAdapter import ChromaAdapter
                from app.adapters.rag.EmbeddingAdapter import EmbeddingAdapter
                self._rag = ChromaAdapter()
                self._embedder = EmbeddingAdapter()
            except Exception as e:
                print(f"⚠️ [PromptBuilder] No se pudieron inicializar adaptadores RAG: {e}", flush=True)
                self._rag = None
                self._embedder = None

    # -----------------------------------------------------------------------
    # Consulta Qdrant para recuerdos conversacionales del usuario
    # -----------------------------------------------------------------------
    def _query_qdrant_context(self, user_id: str, message: str, top_k: int = 5) -> List[str]:
        """
        Recupera los recuerdos vectoriales más relevantes del usuario desde Qdrant.
        Filtra estrictamente por user_id para aislar datos entre clientes.
        Retorna lista de strings (fragmentos de texto para incrustar en el prompt).
        """
        self._ensure_rag()
        if not self._rag or not self._embedder:
            return []
        try:
            from app.adapters.rag.QueryAdapter import _build_filter
            query_emb = self._embedder.embed(message)
            where = _build_filter({"user_id": user_id})
            results = self._rag.query(query_emb, n_results=top_k, where=where)
            return [r["text"] for r in results if r.get("text")]
        except Exception as e:
            print(f"⚠️ [PromptBuilder] Error consultando Qdrant para {user_id}: {e}", flush=True)
            return []

    # -----------------------------------------------------------------------
    # Carga del fichero .txt de plantilla
    # -----------------------------------------------------------------------
    def _load_prompt_template(self, intent: str) -> str:
        """
        Carga el contenido del fichero .txt correspondiente a la intención.
        Si el fichero no existe, retorna un system prompt genérico de emergencia.
        """
        filename = _INTENT_TO_FILE.get(intent.upper(), "prompt_otra.txt")
        path = self.base_prompts_path / filename
        try:
            return path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            print(f"⚠️ [PromptBuilder] Plantilla no encontrada: {path}. Usando genérico.", flush=True)
        except Exception as e:
            print(f"⚠️ [PromptBuilder] Error leyendo plantilla {filename}: {e}", flush=True)
        return (
            "Eres Vainilla, asistente de HellenCommerce. "
            "Responde de forma profesional y concisa en español."
        )

    def _load_multi_intent_template(self) -> str:
        """Carga la plantilla para múltiples intenciones simultáneas."""
        path = self.base_prompts_path / _MULTI_INTENT_FILE
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception as e:
            print(f"⚠️ [PromptBuilder] Error leyendo plantilla multi-intención: {e}", flush=True)
        return (
            "Eres Vainilla, broker de HellenCommerce. "
            "El usuario expresó múltiples intenciones: {intenciones}.\n"
            "Mensaje: {message}\nContexto: {hechos_intenciones}\n"
            "Responde en un solo texto coherente en español."
        )

    # -----------------------------------------------------------------------
    # Ensamblado del prompt final — intención única
    # -----------------------------------------------------------------------
    def _assemble_prompt(
        self,
        system_template: str,
        message: str,
        contexto_lines: List[str],
        rag_snippets: List[str],
        intent: str,
    ) -> str:
        """
        Ensambla el prompt completo que se enviará al modelo en línea:

            [SYSTEM ROLE — contenido del .txt]

            HISTORIAL CONVERSACIONAL:
              <líneas del historial SQLite>

            RECUERDOS RELEVANTES (RAG/Qdrant):
              - <fragmentos semánticos relevantes>

            INTENCIÓN DETECTADA: <INTENT>

            MENSAJE DEL USUARIO:
              <message>
        """
        sections: List[str] = [system_template]

        if contexto_lines:
            sections.append("\nHISTORIAL CONVERSACIONAL:")
            sections.extend(f"  {line}" for line in contexto_lines)

        if rag_snippets:
            sections.append("\nRECUERDOS RELEVANTES (RAG/Qdrant):")
            sections.extend(f"  - {snippet}" for snippet in rag_snippets)

        sections.append(f"\nINTENCIÓN DETECTADA: {intent.upper()}")
        sections.append("\nMENSAJE DEL USUARIO:")
        sections.append(f"  {message}")

        return "\n".join(sections)

    # -----------------------------------------------------------------------
    # Ensamblado del prompt multi-intención
    # -----------------------------------------------------------------------
    def _assemble_multi_intent_prompt(
        self,
        intents: List[str],
        message: str,
        contexto_lines: List[str],
        rag_snippets: List[str],
    ) -> str:
        """
        Rellena las variables del prompt_multi_intencion.txt:
          {intenciones}, {message}, {mercancia}, {hechos_intenciones}
        """
        template = self._load_multi_intent_template()

        intenciones_str = ", ".join(intents)

        hechos_parts: List[str] = []
        if contexto_lines:
            hechos_parts.append("Historial conversacional:\n" + "\n".join(f"  {l}" for l in contexto_lines))
        if rag_snippets:
            hechos_parts.append("Recuerdos RAG/Qdrant:\n" + "\n".join(f"  - {s}" for s in rag_snippets))

        hechos_str = "\n\n".join(hechos_parts) if hechos_parts else "Sin datos adicionales disponibles."
        mercancia_str = contexto_lines[-1] if contexto_lines else message

        return (
            template
            .replace("{intenciones}", intenciones_str)
            .replace("{message}", message)
            .replace("{mercancia}", mercancia_str)
            .replace("{hechos_intenciones}", hechos_str)
        )

    # -----------------------------------------------------------------------
    # Fallback real — usa el .txt como base, nunca strings triviales
    # -----------------------------------------------------------------------
    def _build_fallback_prompt(
        self,
        intent: str,
        message: str,
        contexto_lines: List[str],
    ) -> str:
        """
        Fallback cuando el worker_service no está disponible.
        Usa el .txt real de la intención como system prompt base.
        No consulta Qdrant para no bloquear el flujo de recuperación.
        """
        system_template = self._load_prompt_template(intent)
        return self._assemble_prompt(
            system_template=system_template,
            message=message,
            contexto_lines=contexto_lines,
            rag_snippets=[],
            intent=intent,
        )

    # -----------------------------------------------------------------------
    # Método público principal
    # -----------------------------------------------------------------------
    async def build_prompts(
        self,
        user_id: str,
        message: str,
        intents: List[str],
        contexto: Any = None,
    ) -> Dict[str, str]:
        """
        Genera prompt(s) especializados completos para las intenciones detectadas.

        Flujo:
          - Multi-intención (>= _MULTI_INTENT_THRESHOLD intenciones):
              → construye UN solo prompt con prompt_multi_intencion.txt
              → retorna {"MULTI": "<prompt_completo>"}
              → mistral_service unifica la respuesta final
          - Intención única:
              → carga .txt de la intención (inversión de roles incluida)
              → consulta Qdrant para recuerdos del usuario (filtrado por user_id)
              → ensambla prompt completo
              → envía a worker_service /enrich_prompt para enriquecimiento con BD
              → retorna {"<INTENT>": "<prompt_completo_enriquecido>"}

        Args:
            user_id:   Identificador único del usuario
            message:   Mensaje original del usuario
            intents:   Lista de intenciones detectadas por IntentDetector
            contexto:  Historial conversacional previo (list, dict o None)

        Returns:
            Dict[str, str]  →  {intencion: prompt_completo_ensamblado}
        """
        contexto_lines = self._normalize_contexto(contexto)

        # Consultar Qdrant una sola vez (se reutiliza para todas las intenciones)
        rag_snippets = self._query_qdrant_context(user_id, message)
        print(
            f"🔍 [PromptBuilder] user={user_id} | intents={intents} | "
            f"historial={len(contexto_lines)} líneas | RAG={len(rag_snippets)} fragmentos",
            flush=True,
        )

        # ── MODO MULTI-INTENCIÓN ────────────────────────────────────────────
        if len(intents) >= _MULTI_INTENT_THRESHOLD:
            print(
                f"🔀 [PromptBuilder] Multi-intención ({intents}) → prompt_multi_intencion.txt",
                flush=True,
            )
            multi_prompt = self._assemble_multi_intent_prompt(
                intents=intents,
                message=message,
                contexto_lines=contexto_lines,
                rag_snippets=rag_snippets,
            )
            return {"MULTI": multi_prompt}

        # ── MODO INTENCIÓN ÚNICA ────────────────────────────────────────────
        prompts: Dict[str, str] = {}

        for intent in intents:
            system_template = self._load_prompt_template(intent)
            assembled = self._assemble_prompt(
                system_template=system_template,
                message=message,
                contexto_lines=contexto_lines,
                rag_snippets=rag_snippets,
                intent=intent,
            )
            # Enriquecimiento opcional via worker_service con datos de BD
            enriched = await self._enrich_via_worker(
                user_id=user_id,
                intent=intent,
                assembled_prompt=assembled,
                message=message,
                contexto_lines=contexto_lines,
            )
            prompts[intent] = enriched

        return prompts

    # -----------------------------------------------------------------------
    # Enriquecimiento opcional via worker_service (/enrich_prompt)
    # -----------------------------------------------------------------------
    async def _enrich_via_worker(
        self,
        user_id: str,
        intent: str,
        assembled_prompt: str,
        message: str,
        contexto_lines: List[str],
    ) -> str:
        """
        Envía el prompt ya ensamblado al worker_service para que lo enriquezca
        con datos de la BD (hellencommerce.db / Qdrant business data).

        El worker_service recibe un prompt completo y funcional, y puede añadir
        datos de negocio (vendedores, compradores, negocios) al bloque
        DATOS_DE_LA_BASE_DE_DATOS que los prompts .txt referencian.

        Si el worker_service no está disponible, retorna el prompt tal cual
        (que ya es real y funcional gracias al .txt ensamblado).
        """
        try:
            payload = {
                "user_id": user_id,
                "intent": intent,
                "assembled_prompt": assembled_prompt,
                "message": message,
                "contexto": {"history": contexto_lines, "raw": contexto_lines},
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    # bunker_worker_service/enrich_prompt
                    f"{self.service_url}/enrich_prompt",
                    json=payload,
                )
                if response.status_code == 200:
                    data = response.json()
                    enriched = data.get("enriched_prompt", "").strip()
                    if enriched:
                        print(
                            f"✅ [PromptBuilder] Prompt enriquecido por worker_service → intent={intent}",
                            flush=True,
                        )
                        return enriched
                else:
                    print(
                        f"⚠️ [PromptBuilder] worker_service → HTTP {response.status_code} "
                        f"para intent={intent}. Usando prompt ensamblado localmente.",
                        flush=True,
                    )
        except Exception as e:
            print(
                f"⚠️ [PromptBuilder] worker_service no disponible para intent={intent}: {e}. "
                f"Usando prompt ensamblado localmente.",
                flush=True,
            )

        # El prompt ensamblado localmente ya es completo y funcional
        return assembled_prompt