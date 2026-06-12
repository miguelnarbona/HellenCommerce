import psutil

def listar_sockets():
    conexiones = psutil.net_connections(kind='tcp')
    procesos = {}

    for conn in conexiones:
        pid = conn.pid
        if pid is None:
            continue
        if pid not in procesos:
            try:
                p = psutil.Process(pid)
                procesos[pid] = {
                    "nombre": p.name(),
                    "conexiones": 0
                }
            except psutil.NoSuchProcess:
                continue
        procesos[pid]["conexiones"] += 1

    print("Procesos con más sockets abiertos:")
    for pid, info in sorted(procesos.items(), key=lambda x: x[1]["conexiones"], reverse=True):
        print(f"PID {pid} - {info['nombre']} - {info['conexiones']} conexiones")

if __name__ == "__main__":
    listar_sockets()
