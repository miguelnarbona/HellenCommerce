import asyncio
import random
import time
import httpx
import uuid

API_URL = "http://localhost:8080/chat"

# Mensajes de prueba por intención
mensajes_compra = [
    "¿Tienes arroz disponible?",
    "¿Hay azúcar en venta?",
    "Hola, tendras azucar ?",
    "Hola, tendras arroz ?",
    "Hola, necesito una cerveza fria.",
    "Necesito comprar café.",
    "¿Dónde puedo conseguir frijoles negros?",
    "Quiero saber si hay leche en polvo."
]

mensajes_venta = [
    "Tengo arroz a 20 USD",
    "Busco compradores para frijoles",
    "Tengo azúcar disponible.",
    "Hola, tengo cigarro Hupmman sin filtro a 16 USD la rueda en la localidad de Holguin, gestioname compradores.",
    "Estoy vendiendo café molido a buen precio",
    "Ofrezco aceite de cocina en litros",
    "Hola, busco compradores para huevo a 3000 el carton.",
    "Gestioname compradores para Galeticas Oriol de sabor chocolate"
]

mensajes_servicio = [
    "Necesito un servicio de limpieza",
    "Busco reparación de equipo",
    "Quiero contratar un servicio de transporte.",
    "¿Hay alguien que ofrezca mantenimiento de aire acondicionado?",
    "Necesito un servicio de mensajería urgente",
    "Busco una barberia con urgencia",
    "Sabras por aqui cerca dode venderan libros vijos o de uso ?."
    "Se me rompio el celular, donde puedo arreglarlo ?."
]

mensajes_informativa = [
    "¿Cuál es el precio promedio del arroz en Cuba?",
    "Explícame cómo funciona el registro de vendedores",
    "Quiero información sobre transporte de carga",
    "Hola, necesito pelarme.",
    "Hola, tengo deseos de comer dulces.",
    "¿Qué servicios están disponibles actualmente?",
    "¿Puedes darme detalles sobre cómo recibir notificaciones?"
]

mensajes_negocio = [
    "Quiero abrir una cafetería, ¿qué consejos me das?",
    "Estoy interesado en asociarme para vender productos",
    "¿Cómo puedo mejorar mis ventas de arroz?",
    "Necesito ayuda para negociar con proveedores",
    "¿Qué estrategias recomiendas para atraer clientes?"
]

mensajes_saludo = [
    "Hola, ¿cómo estás?",
    "Buenos días, ¿qué tal?",
    "Saludos, quiero empezar una conversación",
    "Buenas tardes, ¿qué novedades hay?",
    "Hola IA, ¿qué puedes hacer por mí?"
]

mensajes_notificacion = [
    "Quiero registrarme para recibir notificaciones de compradores",
    "Avísame cuando haya vendedores de azúcar",
    "Notifícame si aparece transporte disponible",
    "Quiero activar alertas de nuevos servicios",
    "Regístrame para recibir avisos de café"
]

# Sets de diálogos encadenados para probar continuidad
dialogos_encadenados = [
    # Flujo de compra con aclaración y notificación
    [
        "¿Tienes arroz disponible?",
        "Solo dos porciones por favor.",
        "Quiero registrarme para recibir notificaciones de vendedores de arroz."
    ],
    # Flujo de venta sin resultados
    [
        "Tengo azúcar disponible.",
        "Quiero registrarme como vendedor de azúcar.",
        "Notifícame cuando aparezcan compradores de azúcar."
    ],
    # Flujo de transporte con detalles
    [
        "Quiero contratar un servicio de transporte.",
        "La ciudad origen es Madrid, destino Barcelona. Viajarán 4 personas.",
        "Prefiero un vehículo de pasajeros el sábado por la mañana."
    ],
    # Flujo informativo → negocio → notificación
    [
        "¿Cuál es el precio promedio del arroz en Cuba?",
        "¿Cómo puedo mejorar mis ventas de arroz?",
        "Quiero activar notificaciones de compradores de arroz."
    ],
    # Flujo de aclaración explícito (ACLARAR_INTENCION)
    [
        "Tengo arroz a 20 USD",  # mensaje ambiguo
        "Quiero venderlo en línea",  # aclaración
        "Notifícame cuando aparezcan compradores interesados"  # notificación final
    ]
]

# Generador de mensajes aleatorios
def generar_mensaje():
    categoria = random.choice([
        "compra", "venta", "servicio",
        "informativa", "negocio", "saludo", "notificacion"
    ])
    if categoria == "compra":
        return random.choice(mensajes_compra)
    elif categoria == "venta":
        return random.choice(mensajes_venta)
    elif categoria == "servicio":
        return random.choice(mensajes_servicio)
    elif categoria == "informativa":
        return random.choice(mensajes_informativa)
    elif categoria == "negocio":
        return random.choice(mensajes_negocio)
    elif categoria == "saludo":
        return random.choice(mensajes_saludo)
    else:
        return random.choice(mensajes_notificacion)

async def simular_conversacion(client, user_id, resultados):
    log_file = f"logs_{user_id}.txt"
    with open(log_file, "w", encoding="utf-8") as log:
        log.write(f"=== Conversación {user_id} ===\n")

        # 50% de las veces usamos un set encadenado
        if random.random() < 0.5:
            mensajes = random.choice(dialogos_encadenados)
        else:
            mensajes = [generar_mensaje() for _ in range(random.randint(3, 5))]

        for mensaje in mensajes:
            payload = {"user_id": user_id, "message": mensaje}
            inicio = time.perf_counter()
            try:
                r = await client.post(API_URL, json=payload)
                duracion = time.perf_counter() - inicio
                if r.status_code == 200:
                    resultados["tiempos"].append(duracion)
                    resultados["exitos"] += 1
                else:
                    resultados["errores"] += 1
                data = r.json()
                log.write(f"Usuario: {mensaje}\n")
                log.write(f"IA: {data.get('response')}\n\n")
            except Exception as e:
                resultados["errores"] += 1
                log.write(f"Error: {e}\n")
            await asyncio.sleep(random.uniform(0.2, 1.2))

async def main():
    n = int(input("Número de conversaciones simultáneas: "))
    resultados = {"tiempos": [], "exitos": 0, "errores": 0}
    inicio_total = time.perf_counter()

    async with httpx.AsyncClient(timeout=300.0) as client:
        tareas = [simular_conversacion(client, str(uuid.uuid4()), resultados) for i in range(n)]
        await asyncio.gather(*tareas)

    fin_total = time.perf_counter()
    total_tiempo = fin_total - inicio_total
    total_peticiones = resultados["exitos"] + resultados["errores"]

    print("\n=== MÉTRICAS DE RENDIMIENTO ===")
    print(f"Total de peticiones: {total_peticiones}")
    print(f"Exitosas: {resultados['exitos']}")
    print(f"Errores: {resultados['errores']}")
    if resultados["tiempos"]:
        promedio = sum(resultados["tiempos"]) / len(resultados["tiempos"])
        print(f"Tiempo promedio de respuesta: {promedio:.3f} s")
        print(f"Tiempo mínimo: {min(resultados['tiempos']):.3f} s")
        print(f"Tiempo máximo: {max(resultados['tiempos']):.3f} s")
    print(f"Throughput: {total_peticiones/total_tiempo:.2f} peticiones/segundo")
    print(f"Duración total de la prueba: {total_tiempo:.2f} s")

if __name__ == "__main__":
    asyncio.run(main())
