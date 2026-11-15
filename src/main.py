"""
Multicontacto Inteligente con ESP32 y MicroPython
Proyecto Académico - Servidor Web Embebido, Gestor Wi-Fi y Control de Relevadores

Este programa utiliza 'wifi_manager.py' para conectarse a una red Wi-Fi guardada
en memoria Flash ('wifi_config.json') o levantar un Punto de Acceso seguro ('SmartPS')
con servidor DNS interno (http://smartps.local) para configurar las credenciales
desde cualquier navegador web y conmutar los contactos eléctricos.
"""

import json
import socket
import time
import gc
import machine
from machine import Pin
from wifi_manager import WiFiManager

# ==============================================================================
# 1. CONFIGURACIÓN DEL SISTEMA
# ==============================================================================

# Credenciales del Punto de Acceso (AP) del ESP32 y Clave de Seguridad Web
AP_SSID = 'SmartPS'
AP_PASSWORD = 'SmartPS123'   # WPA2 exige mínimo 8 caracteres
ADMIN_PIN = 'SmartPS'        # Clave solicitada en la web para cambiar el Wi-Fi
HOSTNAME = 'smartps'         # Dominio interno: http://smartps.local

# Credenciales Wi-Fi opcionales por defecto (si no se han configurado desde la web)
WIFI_SSID = 'TU_RED_WIFI'
WIFI_PASSWORD = 'TU_CONTRASEÑA'

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
# 3. GESTIÓN DE RED Y WI-FI MANAGER
# ==============================================================================

wifi = WiFiManager(
    ap_ssid=AP_SSID,
    ap_password=AP_PASSWORD,
    admin_pin=ADMIN_PIN,
    hostname=HOSTNAME,
    default_ssid=WIFI_SSID,
    default_password=WIFI_PASSWORD,
)

# ==============================================================================
# 4. GENERACIÓN DE LA INTERFAZ WEB (HTML + CSS + JavaScript)
# ==============================================================================

def generar_html():
    """Genera la interfaz web con control de relevadores y panel de configuración Wi-Fi."""
    net_status = wifi.get_status()
    if net_status["sta_connected"]:
        status_pill = (
            f'<div class="net-pill net-ok" id="net-pill">'
            f'📶 Conectado a <b>{net_status["sta_ssid"]}</b> ({net_status["sta_ip"]})'
            f'</div>'
        )
    else:
        status_pill = (
            f'<div class="net-pill net-ap" id="net-pill">'
            f'📡 Modo AP Activo: <b>{AP_SSID}</b> (http://{HOSTNAME}.local)'
            f'</div>'
        )

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
    <title>SmartPS | Multicontacto Inteligente</title>
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
            padding: 26px 22px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }}
        header {{
            text-align: center;
            margin-bottom: 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            padding-bottom: 16px;
        }}
        header h1 {{ font-size: 22px; font-weight: 700; color: #38bdf8; }}
        header p {{ font-size: 13px; color: var(--text-muted); margin-top: 4px; }}
        .net-pill {{
            display: inline-block;
            margin-top: 10px;
            font-size: 12px;
            padding: 5px 12px;
            border-radius: 20px;
        }}
        .net-ok {{ background: rgba(16, 185, 129, 0.14); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
        .net-ap {{ background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.35); }}

        .card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 14px;
            padding: 16px 18px;
            margin-bottom: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: border-color 0.15s ease;
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
        input:checked + .slider {{ background-color: var(--switch-active); }}
        input:checked + .slider:before {{ transform: translateX(24px); }}

        .actions {{
            display: flex;
            gap: 10px;
            margin-top: 18px;
        }}
        .btn {{
            flex: 1;
            padding: 11px 12px;
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
        .btn-wifi-toggle {{
            width: 100%;
            margin-top: 12px;
            background: rgba(56, 189, 248, 0.12);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }}

        /* Panel de Configuración Wi-Fi */
        .wifi-panel {{
            display: none;
            margin-top: 16px;
            padding: 16px;
            background: rgba(15, 23, 42, 0.65);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 14px;
        }}
        .wifi-panel.open {{ display: block; }}
        .wifi-panel h4 {{ font-size: 15px; color: #38bdf8; margin-bottom: 12px; }}
        .form-group {{ margin-bottom: 12px; }}
        .form-group label {{
            display: block;
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 5px;
        }}
        .input-row {{ display: flex; gap: 8px; }}
        select, input[type="text"], input[type="password"] {{
            width: 100%;
            padding: 9px 11px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            background: #0f172a;
            color: var(--text-main);
            font-size: 13px;
        }}
        .btn-sm {{
            padding: 9px 12px;
            font-size: 12px;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            background: #334155;
            color: white;
            white-space: nowrap;
        }}
        .btn-save {{ background: #10b981; color: #052e16; font-weight: 700; }}
        .btn-forget {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.35); }}
        .msg-box {{
            display: none;
            margin-top: 12px;
            padding: 10px 12px;
            border-radius: 8px;
            font-size: 12px;
            line-height: 1.45;
        }}
        .msg-ok {{ display: block; background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.35); }}
        .msg-err {{ display: block; background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.35); }}
        .msg-info {{ display: block; background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35); }}
        footer {{ text-align: center; margin-top: 18px; font-size: 11px; color: var(--text-muted); }}
        a {{ color: #38bdf8; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Multicontacto Inteligente</h1>
            <p>SmartPS | ESP32 &amp; MicroPython</p>
            {status_pill}
        </header>

        <div id="relays-list">
            {cards_html}
        </div>

        <div class="actions">
            <button class="btn btn-all-on" onclick="setAll(1)">Encender Todos</button>
            <button class="btn btn-all-off" onclick="setAll(0)">Apagar Todos</button>
        </div>

        <button class="btn btn-wifi-toggle" onclick="toggleWifiPanel()">⚙️ Configurar Red Wi-Fi</button>

        <div class="wifi-panel" id="wifi-panel">
            <h4>Configuración de Red Wi-Fi (2.4 GHz)</h4>

            <div class="form-group">
                <label>1. Selecciona tu red Wi-Fi:</label>
                <div class="input-row">
                    <select id="ssid-select" onchange="onSelectNetwork()">
                        <option value="">-- Presiona Buscar redes --</option>
                    </select>
                    <button class="btn-sm" onclick="scanNetworks()" id="btn-scan">🔍 Buscar</button>
                </div>
            </div>

            <div class="form-group">
                <label>Nombre de red (SSID):</label>
                <input type="text" id="ssid-input" placeholder="Nombre de tu red Wi-Fi">
            </div>

            <div class="form-group">
                <label>2. Contraseña del Wi-Fi:</label>
                <input type="password" id="wifi-pass" placeholder="Contraseña de tu red">
            </div>

            <div class="form-group">
                <label>3. Clave de Seguridad del Dispositivo (SmartPS):</label>
                <input type="password" id="admin-pin" placeholder="Ingresa la clave SmartPS">
            </div>

            <div class="actions">
                <button class="btn btn-save" onclick="saveWifi()">Guardar y Conectar</button>
                <button class="btn btn-forget" onclick="forgetWifi()">Olvidar Red</button>
            </div>

            <div id="wifi-msg" class="msg-box"></div>
        </div>

        <footer>
            <p>Dominio interno: <b>http://{HOSTNAME}.local</b></p>
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
                .catch(err => console.error('Error al conmutar:', err));
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

        function toggleWifiPanel() {{
            const panel = document.getElementById('wifi-panel');
            panel.classList.toggle('open');
            if (panel.classList.contains('open') && document.getElementById('ssid-select').options.length <= 1) {{
                scanNetworks();
            }}
        }}

        function showMsg(text, type) {{
            const box = document.getElementById('wifi-msg');
            box.className = 'msg-box ' + type;
            box.innerHTML = text;
        }}

        function scanNetworks() {{
            const btn = document.getElementById('btn-scan');
            const sel = document.getElementById('ssid-select');
            btn.disabled = true;
            btn.textContent = '⏳...';
            showMsg('Escaneando redes Wi-Fi cercanas...', 'msg-info');

            fetch('/wifi/scan')
                .then(r => r.json())
                .then(list => {{
                    sel.innerHTML = '<option value="">-- Selecciona una red (' + list.length + ' encontradas) --</option>';
                    list.forEach(net => {{
                        const opt = document.createElement('option');
                        opt.value = net.ssid;
                        opt.textContent = net.ssid + ' (' + net.rssi + ' dBm)';
                        sel.appendChild(opt);
                    }});
                    if (list.length > 0) {{
                        sel.value = list[0].ssid;
                        document.getElementById('ssid-input').value = list[0].ssid;
                    }}
                    showMsg('Escaneo completado. Selecciona tu red e ingresa la contraseña.', 'msg-info');
                }})
                .catch(() => showMsg('Error al escanear redes.', 'msg-err'))
                .finally(() => {{
                    btn.disabled = false;
                    btn.textContent = '🔍 Buscar';
                }});
        }}

        function onSelectNetwork() {{
            const val = document.getElementById('ssid-select').value;
            if (val) document.getElementById('ssid-input').value = val;
        }}

        function saveWifi() {{
            const ssid = document.getElementById('ssid-input').value.trim();
            const pass = document.getElementById('wifi-pass').value;
            const pin = document.getElementById('admin-pin').value.trim();

            if (!ssid) {{
                showMsg('Escribe o selecciona el nombre de la red Wi-Fi.', 'msg-err');
                return;
            }}
            if (!pin) {{
                showMsg('Ingresa la clave de seguridad del dispositivo (SmartPS).', 'msg-err');
                return;
            }}

            showMsg('Conectando a <b>' + ssid + '</b> (puede tardar hasta 12 segundos)...', 'msg-info');
            const url = '/wifi/save?ssid=' + encodeURIComponent(ssid) +
                        '&pass=' + encodeURIComponent(pass) +
                        '&pin=' + encodeURIComponent(pin);

            fetch(url)
                .then(r => r.json())
                .then(res => {{
                    if (res.ok) {{
                        showMsg(
                            '✅ <b>¡Conectado con éxito a ' + res.ssid + '!</b><br>' +
                            'Nueva IP asignada: <a href="http://' + res.ip + '">http://' + res.ip + '</a><br>' +
                            'Dominio en tu red: <a href="http://' + res.hostname + '">http://' + res.hostname + '</a>',
                            'msg-ok'
                        );
                        const pill = document.getElementById('net-pill');
                        if (pill) {{
                            pill.className = 'net-pill net-ok';
                            pill.innerHTML = '📶 Conectado a <b>' + res.ssid + '</b> (' + res.ip + ')';
                        }}
                    }} else {{
                        showMsg('❌ ' + res.error, 'msg-err');
                    }}
                }})
                .catch(() => showMsg('Se envió la configuración. Verifica tu conexión a la red local.', 'msg-info'));
        }}

        function forgetWifi() {{
            const pin = document.getElementById('admin-pin').value.trim();
            if (!pin) {{
                showMsg('Ingresa la clave de seguridad (SmartPS) para borrar la red guardada.', 'msg-err');
                return;
            }}
            fetch('/wifi/forget?pin=' + encodeURIComponent(pin))
                .then(r => r.json())
                .then(res => {{
                    if (res.ok) {{
                        showMsg('🗑️ Red olvidada. Punto de Acceso <b>{AP_SSID}</b> activo en http://{HOSTNAME}.local (192.168.4.1).', 'msg-ok');
                    }} else {{
                        showMsg('❌ ' + res.error, 'msg-err');
                    }}
                }})
                .catch(err => console.error(err));
        }}
    </script>
</body>
</html>"""
    return html

# ==============================================================================
# 5. SERVIDOR WEB Y ATENCIÓN DE PETICIONES
# ==============================================================================

def url_decode(val: str) -> str:
    """Decodifica caracteres especiales URL (%20, %40, +, etc.) para SSIDs y contraseñas."""
    if not val:
        return ""
    val = val.replace("+", " ")
    parts = val.split("%")
    if len(parts) == 1:
        return val
    out = [parts[0]]
    for item in parts[1:]:
        if len(item) >= 2:
            try:
                out.append(chr(int(item[:2], 16)) + item[2:])
            except ValueError:
                out.append("%" + item)
        else:
            out.append("%" + item)
    return "".join(out)

def parse_query_params(path):
    """Extrae y decodifica parámetros GET de la query string."""
    params = {}
    if '?' in path:
        query_string = path.split('?', 1)[1].split(' ')[0]
        pairs = query_string.split('&')
        for pair in pairs:
            if '=' in pair:
                key, val = pair.split('=', 1)
                params[url_decode(key)] = url_decode(val)
    return params

def send_json(conn, payload_obj, status="200 OK"):
    body = json.dumps(payload_obj)
    headers = (
        f"HTTP/1.1 {status}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n"
        "Connection: close\r\n\r\n"
    )
    conn.send(headers.encode("utf-8"))
    conn.send(body.encode("utf-8"))

def iniciar_servidor():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', 80))
    s.listen(5)
    # Timeout corto para intercalar atención HTTP (puerto 80) y DNS local (puerto 53)
    s.settimeout(0.05)
    print(f"Servidor web activo en http://{HOSTNAME}.local (Puerto 80)...\n")

    gc_counter = 0
    while True:
        try:
            # Procesar consultas DNS del dominio interno y tareas del WiFiManager
            wifi.tick()

            gc_counter += 1
            if gc_counter >= 100:
                gc.collect()
                gc_counter = 0

            try:
                conn, addr = s.accept()
            except OSError:
                # No hay nueva conexión HTTP en este ciclo (timeout de 50ms)
                continue

            conn.settimeout(3.0)
            request_bytes = conn.recv(1024)
            request = request_bytes.decode('utf-8', 'ignore')
            
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
                conn.send(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
                conn.close()
                continue

            # 2. Endpoint API: Conmutar un relevador específico (/set?id=0&val=1)
            if path.startswith('/set?'):
                params = parse_query_params(path)
                relay_id = int(params.get('id', -1))
                val = int(params.get('val', -1))
                
                if 0 <= relay_id < len(relays) and val in (0, 1):
                    set_relay(relay_id, bool(val))
                    send_json(conn, {"id": relay_id, "is_on": relays[relay_id]["is_on"]})
                else:
                    conn.send(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
                conn.close()
                continue

            # 3. Endpoint API: Encender o apagar todos (/set_all?val=1)
            if path.startswith('/set_all?'):
                params = parse_query_params(path)
                val = int(params.get('val', 0))
                for r in relays:
                    set_relay(r["id"], bool(val))
                
                items = [{"id": r["id"], "is_on": r["is_on"]} for r in relays]
                send_json(conn, items)
                conn.close()
                continue

            # 4. Endpoint Wi-Fi: Escanear redes cercanas (/wifi/scan)
            if path.startswith('/wifi/scan'):
                networks = wifi.scan_networks()
                send_json(conn, networks)
                conn.close()
                continue

            # 5. Endpoint Wi-Fi: Guardar y conectar a nueva red (/wifi/save?ssid=...&pass=...&pin=...)
            if path.startswith('/wifi/save?'):
                params = parse_query_params(path)
                ssid = params.get('ssid', '').strip()
                password = params.get('pass', '')
                pin = params.get('pin', '').strip()
                result = wifi.configure_new_network(ssid, password, pin)
                send_json(conn, result)
                conn.close()
                continue

            # 6. Endpoint Wi-Fi: Olvidar red actual y volver a modo AP (/wifi/forget?pin=...)
            if path.startswith('/wifi/forget?'):
                params = parse_query_params(path)
                pin = params.get('pin', '').strip()
                if pin != ADMIN_PIN:
                    send_json(conn, {"ok": False, "error": "Clave de seguridad incorrecta."})
                else:
                    wifi.clear_config()
                    send_json(conn, {"ok": True})
                conn.close()
                continue

            # 7. Endpoint Wi-Fi: Consultar estado actual (/wifi/status)
            if path.startswith('/wifi/status'):
                send_json(conn, wifi.get_status())
                conn.close()
                continue

            # 8. Ruta Principal (y detección de Portal Cautivo): Retornar interfaz HTML
            html_content = generar_html()
            html_bytes = html_content.encode('utf-8')
            response_headers = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html; charset=UTF-8\r\n"
                "Content-Length: " + str(len(html_bytes)) + "\r\n"
                "Connection: close\r\n\r\n"
            )
            conn.send(response_headers.encode('utf-8'))
            conn.sendall(html_bytes)
            conn.close()

        except Exception:
            try:
                conn.close()
            except Exception:
                pass

# ==============================================================================
# 6. FLUJO DE EJECUCIÓN PRINCIPAL
# ==============================================================================
try:
    ip_asignada = wifi.auto_connect()
    iniciar_servidor()
except KeyboardInterrupt:
    print("\nServidor detenido manualmente por el usuario.")
except Exception as err:
    print(f"\nError crítico: {err}")
    time.sleep(3)
    machine.reset()
