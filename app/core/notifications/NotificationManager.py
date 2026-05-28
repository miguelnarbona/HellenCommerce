# app/core/notifications/NotificationManager.py

import threading
import time
import logging

logging.basicConfig(level=logging.INFO)


class NotificationManager:
    """
    Administra el ciclo de vida de las notificaciones:
    - Lee notificaciones pendientes desde SQLiteAdapter.
    - Intenta enviarlas usando MQTTAdapter.
    - Marca como enviadas o reintenta más tarde.
    - Permite marcar como leídas desde el cliente Android.
    """

    def __init__(self, db, mqtt, interval=5):
        self.db = db
        self.mqtt = mqtt
        self.interval = interval
        self._running = True

        # Hilo en segundo plano
        threading.Thread(target=self._loop, daemon=True).start()

    # ---------------------------------------------------------
    # Bucle principal
    # ---------------------------------------------------------
    def _loop(self):
        while self._running:
            try:
                pendientes = self._obtener_pendientes()

                for notif in pendientes:
                    self._procesar_notificacion(notif)

            except Exception as e:
                logging.error(f"[NotificationManager] Error en loop: {e}")

            time.sleep(self.interval)

    # ---------------------------------------------------------
    # Obtener notificaciones pendientes (delegado a SQLiteAdapter)
    # ---------------------------------------------------------
    def _obtener_pendientes(self):
        return self.db.obtener_notificaciones_pendientes()

    # ---------------------------------------------------------
    # Procesar una notificación
    # ---------------------------------------------------------
    def _procesar_notificacion(self, notif):
        notif_id = notif["id"]
        user_id = notif["user_id"]
        topic = f"notificaciones/{user_id}"
        mensaje = notif["mensaje"]

        logging.info(f"[NotificationManager] Enviando notif {notif_id} a {user_id}...")

        enviado = self.mqtt.publish(topic, mensaje)

        if enviado:
            self._marcar_enviada(notif_id)
        else:
            logging.warning(f"[NotificationManager] Fallo al enviar notif {notif_id}. Reintentará.")

    # ---------------------------------------------------------
    # Marcar como enviada (delegado a SQLiteAdapter)
    # ---------------------------------------------------------
    def _marcar_enviada(self, notif_id):
        self.db.marcar_notificacion_enviada(notif_id)

    # ---------------------------------------------------------
    # Marcar como leída (solo este método toca SQL directo)
    # ---------------------------------------------------------
    def marcar_leida(self, notif_id):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            UPDATE notificaciones
            SET estado = 'leida',
                fecha_lectura = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (notif_id,))
        self.db.conn.commit()

    # ---------------------------------------------------------
    # Detener el manager
    # ---------------------------------------------------------
    def stop(self):
        self._running = False
