"""
Multicontacto Inteligente con ESP32 y MicroPython
Proyecto Académico - Servidor Web Embebido y Control de Relevadores

Este programa levanta un punto de acceso o se conecta a una red Wi-Fi local
y expone un servidor HTTP con una interfaz web responsiva para controlar
múltiples relevadores conectados a tomacorrientes eléctricos.
"""

import network
import socket
import time
import gc
from machine import Pin

# ==============================================================================
# 1. CONFIGURACIÓN DEL SISTEMA
# ==============================================================================

# Credenciales de tu red Wi-Fi (Modifica estos valores)
WIFI_SSID = 'TU_RED_WIFI'
WIFI_PASSWORD = 'TU_CONTRASEÑA'

# Modo Punto de Acceso (AP) como respaldo si falla la conexión Wi-Fi:
AP_FALLBACK = True
AP_SSID = 'ESP32-Multicontacto'
AP_PASSWORD = 'multicontacto123'  # Mínimo 8 caracteres

# NOTA DE SEGURIDAD SOBRE RELEVADORES:
# La gran mayoría de los módulos de relevadores de 5V para Arduino/ESP32 son
# ACTIVOS EN BAJO (Active LOW), lo que significa:
#   - 0 lógico (0V) -> Relevador ACTIVO (Contacto CERRADO / Conduce corriente)
#   - 1 lógico (3.3V) -> Relevador INACTIVO (Contacto ABIERTO / Corta corriente)
# Si tu módulo es Activo en Alto (Active HIGH), cambia esta variable a False.
RELAY_ACTIVE_LOW = True

# Asignación de pines GPIO y nombres para cada contacto.
# Pines recomendados en ESP32 para salidas seguras: 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33.
# Evitar pines strapping (0, 2, 12, 15) o pines solo entrada (34 a 39).
RELAYS_CONFIG = [
    {"id": 0, "name": "Contacto 1 (Lámpara)", "pin": 16},
    {"id": 1, "name": "Contacto 2 (Cargador)", "pin": 17},
    {"id": 2, "name": "Contacto 3 (Monitor)", "pin": 18},
    {"id": 3, "name": "Contacto 4 (Auxiliar)", "pin": 19},
]

# ==============================================================================
# 2. INICIALIZACIÓN DE HARDWARE (RELEVADORES)
# ==============================================================================

def get_physical_value(is_on: bool) -> int:
    """Convierte el estado lógico deseado (True=Encendido, False=Apagado) al nivel físico del pin."""
    if RELAY_ACTIVE_LOW:
        return 0 if is_on else 1
    else:
        return 1 if is_on else 0

relays = []
for config in RELAYS_CONFIG:
    pin_obj = Pin(config["pin"], Pin.OUT)
    # Por seguridad, asegurar que todos los relevadores inicien APAGADOS (circuito abierto)
    pin_obj.value(get_physical_value(False))
    
    relays.append({
        "id": config["id"],
        "name": config["name"],
        "pin_num": config["pin"],
        "pin_obj": pin_obj,
        "is_on": False
    })

def set_relay(relay_id: int, state: bool):
    """Enciende (True) o apaga (False) el relevador indicado por su id."""
    if 0 <= relay_id < len(relays):
        relays[relay_id]["is_on"] = state
        relays[relay_id]["pin_obj"].value(get_physical_value(state))
        print(f"[{relays[relay_id]['name']}] -> {'ENCENDIDO' if state else 'APAGADO'}")

def toggle_relay(relay_id: int) -> bool:
    """Alterna el estado del relevador indicado y retorna el nuevo estado."""
    if 0 <= relay_id < len(relays):
        new_state = not relays[relay_id]["is_on"]
        set_relay(relay_id, new_state)
        return new_state
    return False

# ==============================================================================
# 3. GESTIÓN DE CONEXIÓN DE RED (Wi-Fi STA y fallback AP)
# ==============================================================================

def conectar_red():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    print(f"Intentando conectar a Wi-Fi '{WIFI_SSID}'...")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    
    # Timeout de 20 intentos (~10 segundos)
    intentos = 0
    while not wlan.isconnected() and intentos < 20:
        time.sleep(0.5)
        print(".", end="")
        intentos += 1
    print("")

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print("=" * 45)
        print(f" Wi-Fi Conectado con éxito!")
        print(f" Direccion IP asignada: http://{ip}")
        print("=" * 45)
        return ip
    else:
        print(" No fue posible conectar a la red Wi-Fi.")
        if AP_FALLBACK:
            print(f" Levantando Modo Punto de Acceso (AP): {AP_SSID}")
            ap = network.WLAN(network.AP_IF)
            ap.active(True)
            ap.config(essid=AP_SSID, password=AP_PASSWORD, authmode=network.AUTH_WPA_WPA2_PSK)
            ip = ap.ifconfig()[0]
            print(f" Conéctate a la red Wi-Fi: '{AP_SSID}'")
            print(f" Contraseña: '{AP_PASSWORD}'")
            print(f" Luego entra a: http://{ip}")
            print("=" * 45)
            return ip
        else:
            raise RuntimeError("Fallo de conexión Wi-Fi y AP de respaldo desactivado.")

# ==============================================================================
# 4. GENERACIÓN DE LA INTERFAZ WEB (HTML + CSS + JavaScript)
# ==============================================================================

def generar_html():
    """Genera una página web moderna con tarjetas e interruptores deslizables (toggle switches)."""
    cards_html = ""
    for r in relays:
        checked = "checked" if r["is_on"] else ""
        badge_class = "badge-on" if r["is_on"] else "badge-off"
        badge_text = "ENCENDIDO" if r["is_on"] else "APAGADO"
        
        cards_html += f"""
        <div class="card" id="card-{r['id']}">
            <div class="card-info">
                <h3>{r['name']}</h3>
                <span class="badge {badge_class}" id="badge-{r['id']}">{badge_text}</span>
                <span class="pin-info">GPIO {r['pin_num']}</span>
            </div>
            <label class="switch">
                <input type="checkbox" id="switch-{r['id']}" {checked} onchange="toggleRelay({r['id']}, this.checked)">
                <span class="slider"></span>
            </label>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Multicontacto Inteligente ESP32</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-on: #10b981;
            --accent-off: #64748b;
            --switch-bg: #334155;
            --switch-active: #3b82f6;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            width: 100%;
            max-width: 480px;
            background: var(--card-bg);
            border-radius: 20px;
            padding: 28px 24px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }}
        header {{
            text-align: center;
            margin-bottom: 24px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            padding-bottom: 16px;
        }}
        header h1 {{ font-size: 22px; font-weight: 700; color: #38bdf8; }}
        header p {{ font-size: 13px; color: var(--text-muted); margin-top: 4px; }}
        
        .card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 14px;
            padding: 16px 18px;
            margin-bottom: 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: transform 0.15s ease, border-color 0.15s ease;
        }}
        .card:hover {{ border-color: rgba(56, 189, 248, 0.3); }}
        .card-info h3 {{ font-size: 16px; font-weight: 600; margin-bottom: 6px; }}
        .pin-info {{ font-size: 11px; color: var(--text-muted); margin-left: 8px; }}
        .badge {{
            display: inline-block;
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 12px;
            text-transform: uppercase;
        }}
        .badge-on {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
        .badge-off {{ background: rgba(100, 116, 139, 0.15); color: #94a3b8; border: 1px solid rgba(100, 116, 139, 0.3); }}

        /* Switch Toggle */
        .switch {{
            position: relative;
            display: inline-block;
            width: 56px;
            height: 32px;
            flex-shrink: 0;
        }}
        .switch input {{ opacity: 0; width: 0; height: 0; }}
        .slider {{
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: var(--switch-bg);
            transition: .25s;
            border-radius: 34px;
        }}
        .slider:before {{
            position: absolute;
            content: "";
            height: 24px;
            width: 24px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            transition: .25s;
            border-radius: 50%;
            box-shadow: 0 2px 5px rgba(0,0,0,0.3);
        }}
        input:checked + .slider {{
            background-color: var(--switch-active);
        }}
        input:checked + .slider:before {{
            transform: translateX(24px);
        }}

        .actions {{
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }}
        .btn {{
            flex: 1;
            padding: 10px;
            border: none;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s;
        }}
        .btn:active {{ opacity: 0.8; }}
        .btn-all-on {{ background-color: #2563eb; color: white; }}
        .btn-all-off {{ background-color: #475569; color: white; }}
        footer {{ text-align: center; margin-top: 20px; font-size: 11px; color: var(--text-muted); }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Multicontacto Inteligente</h1>
            <p>Control Remoto IoT | ESP32 & MicroPython</p>
        </header>

        <div id="relays-list">
            {cards_html}
        </div>

        <div class="actions">
            <button class="btn btn-all-on" onclick="setAll(1)">Encender Todos</button>
            <button class="btn btn-all-off" onclick="setAll(0)">Apagar Todos</button>
        </div>

        <footer>
            <p>Estado en tiempo real | Red Local</p>
        </footer>
    </div>

    <script>
        function toggleRelay(id, state) {{
            const val = state ? 1 : 0;
            fetch('/set?id=' + id + '&val=' + val)
                .then(response => response.json())
                .then(data => {{
                    updateBadge(data.id, data.is_on);
                }})
                .catch(err => {{
                    console.error('Error al conmutar:', err);
                }});
        }}

        function setAll(val) {{
            fetch('/set_all?val=' + val)
                .then(response => response.json())
                .then(data => {{
                    data.forEach(r => {{
                        const sw = document.getElementById('switch-' + r.id);
                        if (sw) sw.checked = r.is_on;
                        updateBadge(r.id, r.is_on);
                    }});
                }})
                .catch(err => console.error(err));
        }}

        function updateBadge(id, isOn) {{
            const badge = document.getElementById('badge-' + id);
            if (!badge) return;
            if (isOn) {{
                badge.className = 'badge badge-on';
                badge.textContent = 'ENCENDIDO';
            }} else {{
                badge.className = 'badge badge-off';
                badge.textContent = 'APAGADO';
            }}
        }}
    </script>
</body>
</html>"""
    return html

# ==============================================================================
# 5. SERVIDOR WEB Y ATENCIÓN DE PETICIONES
# ==============================================================================

def parse_query_params(path):
    """Extrae parámetros GET de la query string (ej: '/set?id=1&val=0')."""
    params = {}
    if '?' in path:
        query_string = path.split('?')[1].split(' ')[0]
        pairs = query_string.split('&')
        for pair in pairs:
            if '=' in pair:
                key, val = pair.split('=', 1)
                params[key] = val
    return params

def iniciar_servidor():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', 80))
    s.listen(5)
    print("Servidor web iniciado y esperando peticiones en el puerto 80...\n")

    while True:
        try:
            # Forzar recolección de basura para evitar fragmentación de RAM
            gc.collect()

            conn, addr = s.accept()
            conn.settimeout(3.0)  # Evita que conexiones colgadas bloqueen el microcontrolador
            request_bytes = conn.recv(1024)
            request = request_bytes.decode('utf-8')
            
            if not request:
                conn.close()
                continue
                
            first_line = request.split('\r\n')[0]
            parts = first_line.split(' ')
            if len(parts) < 2:
                conn.close()
                continue
                
            path = parts[1]
            
            # 1. Ignorar solicitudes de favicon para ahorrar tiempo y recursos
            if path == '/favicon.ico':
                conn.send("HTTP/1.1 404 Not Found\r\n\r\n".encode('utf-8'))
                conn.close()
                continue

            # 2. Endpoint API: Conmutar un relevador específico (/set?id=0&val=1)
            if path.startswith('/set?'):
                params = parse_query_params(path)
                relay_id = int(params.get('id', -1))
                val = int(params.get('val', -1))
                
                if 0 <= relay_id < len(relays) and val in (0, 1):
                    set_relay(relay_id, bool(val))
                    status_json = f'{{"id": {relay_id}, "is_on": {str(relays[relay_id]["is_on"]).lower()}}}'
                    response = (
                        "HTTP/1.1 200 OK\r\n"
                        "Content-Type: application/json\r\n"
                        "Connection: close\r\n\r\n" + status_json
                    )
                else:
                    response = "HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n"
                
                conn.send(response.encode('utf-8'))
                conn.close()
                continue

            # 3. Endpoint API: Encender o apagar todos (/set_all?val=1)
            if path.startswith('/set_all?'):
                params = parse_query_params(path)
                val = int(params.get('val', 0))
                for r in relays:
                    set_relay(r["id"], bool(val))
                
                items = [f'{{"id": {r["id"]}, "is_on": {str(r["is_on"]).lower()}}}' for r in relays]
                status_json = "[" + ",".join(items) + "]"
                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json\r\n"
                    "Connection: close\r\n\r\n" + status_json
                )
                conn.send(response.encode('utf-8'))
                conn.close()
                continue

            # 4. Ruta Principal: Retornar la interfaz HTML completa
            html_content = generar_html()
            response_headers = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html; charset=UTF-8\r\n"
                "Content-Length: " + str(len(html_content.encode('utf-8'))) + "\r\n"
                "Connection: close\r\n\r\n"
            )
            conn.send(response_headers.encode('utf-8'))
            conn.send(html_content.encode('utf-8'))
            conn.close()

        except Exception as e:
            # Manejo de excepciones de socket/timeout
            try:
                conn.close()
            except:
                pass

# ==============================================================================
# 6. FLUJO DE EJECUCIÓN PRINCIPAL
# ==============================================================================
try:
    ip_asignada = conectar_red()
    iniciar_servidor()
except KeyboardInterrupt:
    print("\nServidor detenido manualmente por el usuario.")
except Exception as err:
    print(f"\nError crítico: {err}")
