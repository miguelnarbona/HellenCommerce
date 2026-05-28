# app/adapters/mqtt/MQTTAdapter.py

import paho.mqtt.client as mqtt
import threading
import time
import logging

logging.basicConfig(level=logging.INFO)

class MQTTAdapter:
    """
    Cliente MQTT para publicar notificaciones al broker Mosquitto.
    Seguro para producción, con reconexión automática y thread interno.
    """

    def __init__(self, host="mosquitto", port=1883, keepalive=300):
        self.host = host
        self.port = port
        self.keepalive = keepalive

        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        self._connected = False
        self._lock = threading.Lock()

        self._start()

    # ---------------------------------------------------------
    # Conexión inicial + hilo de reconexión
    # ---------------------------------------------------------
    def _start(self):
        threading.Thread(target=self._connect_loop, daemon=True).start()

    def _connect_loop(self):
        while True:
            if not self._connected:
                try:
                    logging.info(f"[MQTT] Conectando a {self.host}:{self.port} ...")
                    self.client.connect(
                        host=self.host, 
                        port=int(self.port), 
                        keepalive=self.keepalive
                        )
                    self.client.loop_start()
                except Exception as e:
                    logging.error(f"[MQTT] Error de conexión: {e}")
            time.sleep(3)

    # ---------------------------------------------------------
    # Eventos MQTT
    # ---------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            logging.info("[MQTT] Conectado correctamente al broker.")
        else:
            logging.error(f"[MQTT] Fallo de conexión. Código: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        logging.warning("[MQTT] Desconectado del broker. Reintentando...")

    # ---------------------------------------------------------
    # Publicación segura
    # ---------------------------------------------------------
    def publish(self, topic: str, message: str):
        with self._lock:
            if not self._connected:
                logging.warning("[MQTT] No conectado. Mensaje no enviado.")
                return False

            try:
                self.client.publish(topic, message)
                logging.info(f"[MQTT] Publicado en {topic}: {message}")
                return True
            except Exception as e:
                logging.error(f"[MQTT] Error publicando en {topic}: {e}")
                return False
