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

# Archivo donde se guardan los nombres personalizados de cada contacto
NAMES_FILE = 'relays_names.json'

# NOTA DE SEGURIDAD SOBRE RELEVADORES:
# La gran mayoría de los módulos de relevadores de 5V para Arduino/ESP32 son
# ACTIVOS EN BAJO (Active LOW), lo que significa:
#   - 0 lógico (0V) -> Relevador ACTIVO (Contacto CERRADO / Conduce corriente)
#   - 1 lógico (3.3V) -> Relevador INACTIVO (Contacto ABIERTO / Corta corriente)
# Si tu módulo es Activo en Alto (Active HIGH), cambia esta variable a False.
RELAY_ACTIVE_LOW = True

# Asignación de pines GPIO y nombres por defecto para cada contacto.
# En ESP32-S3, los pines 19 y 20 corresponden al puerto USB nativo (D- y D+),
# por lo que se usan los pines consecutivos seguros 15, 16, 17 y 18.
RELAYS_CONFIG = [
    {"id": 0, "name": "Contacto 1", "pin": 15},
    {"id": 1, "name": "Contacto 2", "pin": 16},
    {"id": 2, "name": "Contacto 3", "pin": 17},
    {"id": 3, "name": "Contacto 4", "pin": 18},
]

# ==============================================================================
# 2. INICIALIZACIÓN DE HARDWARE Y NOMBRES PERSONALIZADOS
# ==============================================================================

def load_custom_names() -> dict:
    """Carga los nombres personalizados de los contactos desde la memoria Flash."""
    try:
        with open(NAMES_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

def save_custom_names():
    """Guarda los nombres actuales de los contactos en la memoria Flash."""
    try:
        data = {str(r["id"]): r["name"] for r in relays}
        with open(NAMES_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error al guardar nombres: {e}")

def get_physical_value(is_on: bool) -> int:
    """Convierte el estado lógico deseado (True=Encendido, False=Apagado) al nivel físico del pin."""
    if RELAY_ACTIVE_LOW:
        return 0 if is_on else 1
    else:
        return 1 if is_on else 0

saved_names = load_custom_names()
relays = []
for config in RELAYS_CONFIG:
    pin_obj = Pin(config["pin"], Pin.OUT)
    # Por seguridad, asegurar que todos los relevadores inicien APAGADOS (circuito abierto)
    pin_obj.value(get_physical_value(False))
    custom_name = saved_names.get(str(config["id"]), config["name"])
    
    relays.append({
        "id": config["id"],
        "name": custom_name,
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

def rename_relay(relay_id: int, new_name: str) -> bool:
    """Cambia y guarda el nombre personalizado de un contacto."""
    clean_name = new_name.strip()
    if 0 <= relay_id < len(relays) and clean_name:
        relays[relay_id]["name"] = clean_name[:32]
        save_custom_names()
        print(f"[Contacto {relay_id + 1}] renombrado a: '{relays[relay_id]['name']}'")
        return True
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

def get_full_net_status() -> dict:
    """Obtiene el estado de red de forma segura incluso si wifi_manager tiene versión previa."""
    st = wifi.get_status()
    if "sta_netmask" not in st:
        st["sta_netmask"] = ""
        st["sta_gateway"] = ""
        st["sta_dns"] = ""
        st["sta_rssi"] = None
        st["sta_channel"] = None
        st["mac"] = ""
        try:
            mac_bytes = wifi.sta.config("mac")
            st["mac"] = ":".join(f"{b:02X}" for b in mac_bytes)
        except Exception:
            pass
        if st.get("sta_connected"):
            try:
                ifc = wifi.sta.ifconfig()
                st["sta_ip"] = ifc[0]
                st["sta_netmask"] = ifc[1]
                st["sta_gateway"] = ifc[2]
                st["sta_dns"] = ifc[3]
            except Exception:
                pass
            try:
                st["sta_rssi"] = wifi.sta.status("rssi")
            except Exception:
                pass
            try:
                st["sta_channel"] = wifi.sta.config("channel")
            except Exception:
                pass
    return st

# ==============================================================================
# 4. GENERACIÓN DE LA INTERFAZ WEB (HTML + CSS + JavaScript)
# ==============================================================================

def html_escape(text) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

def generar_html() -> str:
    """Genera la interfaz web con pantalla de inicio en modo AP, interruptores editables y gestor Wi-Fi."""
    net_status = get_full_net_status()
    sta_ok = bool(net_status.get("sta_connected"))
    is_ap_only = not sta_ok

    sta_ssid = html_escape(net_status.get("sta_ssid", ""))
    sta_ip = html_escape(net_status.get("sta_ip", ""))
    sta_gw = html_escape(net_status.get("sta_gateway", "-"))
    sta_mask = html_escape(net_status.get("sta_netmask", "-"))
    sta_dns = html_escape(net_status.get("sta_dns", "-"))
    rssi_val = net_status.get("sta_rssi")
    chan_val = net_status.get("sta_channel")
    rssi_str = f"{rssi_val} dBm" if rssi_val is not None else "N/D"
    chan_str = f"Canal {chan_val} (2.4 GHz)" if chan_val is not None else "2.4 GHz"
    mac_str = html_escape(net_status.get("mac") or "N/D")

    if sta_ok:
        status_pill = (
            f'<div class="net-pill net-ok" id="net-pill">'
            f'Conectado a <b>{sta_ssid}</b> ({sta_ip})'
            f'</div>'
        )
    else:
        status_pill = (
            f'<div class="net-pill net-ap" id="net-pill">'
            f'Modo AP Activo: <b>{AP_SSID}</b> (http://{HOSTNAME}.local)'
            f'</div>'
        )

    welcome_class = "view active" if is_ap_only else "view"
    relays_class = "view" if is_ap_only else "view active"
    relays_back_btn = (
        '<div class="top-nav"><button class="btn-nav-back" onclick="goBack(\'welcome\')">Atrás</button></div>'
        if is_ap_only
        else ""
    )

    cards_html = ""
    for r in relays:
        rid = r["id"]
        safe_name = html_escape(r["name"])
        checked = "checked" if r["is_on"] else ""
        badge_class = "badge-on" if r["is_on"] else "badge-off"
        badge_text = "ENCENDIDO" if r["is_on"] else "APAGADO"
        
        cards_html += (
            f'<div class="card" id="card-{rid}">'
            f'<div class="card-info">'
            f'<div class="title-row" id="title-row-{rid}">'
            f'<h3 id="name-text-{rid}">{safe_name}</h3>'
            f'<button class="btn-icon" onclick="openRename({rid})">Editar</button>'
            f'</div>'
            f'<div class="rename-row" id="rename-row-{rid}">'
            f'<input type="text" id="rename-input-{rid}" value="{safe_name}" maxlength="32">'
            f'<button class="btn-mini btn-mini-ok" onclick="saveRename({rid})">Guardar</button>'
            f'<button class="btn-mini btn-mini-cancel" onclick="closeRename({rid})">Cancelar</button>'
            f'</div>'
            f'<span class="badge {badge_class}" id="badge-{rid}">{badge_text}</span>'
            f'<span class="pin-info">GPIO {r["pin_num"]}</span>'
            f'</div>'
            f'<label class="switch">'
            f'<input type="checkbox" id="switch-{rid}" {checked} onchange="toggleRelay({rid}, this.checked)">'
            f'<span class="slider"></span>'
            f'</label>'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
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
  box-shadow: 0 20px 40px rgba(0,0,0,0.4);
  border: 1px solid rgba(255,255,255,0.08);
}}
header {{
  text-align: center;
  margin-bottom: 18px;
  border-bottom: 1px solid rgba(255,255,255,0.1);
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
.net-ok {{ background: rgba(16,185,129,0.14); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }}
.net-ap {{ background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.35); }}
.view {{ display: none; }}
.view.active {{ display: block; }}
.top-nav {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }}
.btn-nav-back {{
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(255,255,255,0.16);
  color: var(--text-main);
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}}
.btn-nav-back:hover {{ background: rgba(255,255,255,0.13); border-color: rgba(56,189,248,0.4); }}
.wifi-tabs {{ display: flex; gap: 8px; margin-bottom: 14px; }}
.tab-btn {{
  flex: 1;
  padding: 9px 10px;
  border-radius: 9px;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(15,23,42,0.5);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}}
.tab-btn.active {{
  background: rgba(56,189,248,0.16);
  color: #38bdf8;
  border-color: rgba(56,189,248,0.45);
}}
.info-list {{
  background: rgba(15,23,42,0.55);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 6px 14px;
  margin-bottom: 14px;
}}
.info-row {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 9px 0;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  font-size: 13px;
}}
.info-row:last-child {{ border-bottom: none; }}
.info-label {{ color: var(--text-muted); font-size: 12px; }}
.info-val {{ color: var(--text-main); font-weight: 600; text-align: right; }}
.section-divider {{ margin-top: 16px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,0.08); }}
.welcome-box {{ text-align: center; padding: 10px 6px 6px; }}
.welcome-box h2 {{ font-size: 19px; color: var(--text-main); margin-bottom: 8px; }}
.welcome-box p {{ font-size: 13px; color: var(--text-muted); line-height: 1.5; margin-bottom: 22px; }}
.welcome-actions {{ display: flex; flex-direction: column; gap: 12px; }}
.btn-hero {{
  width: 100%;
  padding: 15px 16px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  border: none;
}}
.btn-hero-wifi {{ background: linear-gradient(135deg, #2563eb, #0284c7); color: white; }}
.btn-hero-switches {{ background: rgba(255,255,255,0.06); color: var(--text-main); border: 1px solid rgba(255,255,255,0.15); }}
.card {{
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.05);
  border-radius: 14px;
  padding: 16px 18px;
  margin-bottom: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}}
.card-info {{ flex: 1; min-width: 0; }}
.title-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.title-row h3 {{ font-size: 16px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.btn-icon {{
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 11px;
  padding: 3px 8px;
  cursor: pointer;
}}
.rename-row {{ display: none; align-items: center; gap: 6px; margin-bottom: 8px; }}
.rename-row.open {{ display: flex; }}
.rename-row input {{ padding: 6px 9px; font-size: 13px; border-radius: 6px; }}
.btn-mini {{ border: none; border-radius: 6px; padding: 6px 9px; font-size: 12px; font-weight: 600; cursor: pointer; }}
.btn-mini-ok {{ background: #10b981; color: #052e16; }}
.btn-mini-cancel {{ background: #475569; color: white; }}
.pin-info {{ font-size: 11px; color: var(--text-muted); margin-left: 8px; }}
.badge {{ display: inline-block; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 12px; text-transform: uppercase; }}
.badge-on {{ background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }}
.badge-off {{ background: rgba(100,116,139,0.15); color: #94a3b8; border: 1px solid rgba(100,116,139,0.3); }}
.switch {{ position: relative; display: inline-block; width: 56px; height: 32px; flex-shrink: 0; }}
.switch input {{ opacity: 0; width: 0; height: 0; }}
.slider {{ position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: var(--switch-bg); transition: .25s; border-radius: 34px; }}
.slider:before {{ position: absolute; content: ""; height: 24px; width: 24px; left: 4px; bottom: 4px; background-color: white; transition: .25s; border-radius: 50%; }}
input:checked + .slider {{ background-color: var(--switch-active); }}
input:checked + .slider:before {{ transform: translateX(24px); }}
.actions {{ display: flex; gap: 10px; margin-top: 16px; }}
.btn {{ flex: 1; padding: 11px 12px; border: none; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer; }}
.btn-all-on {{ background-color: #2563eb; color: white; }}
.btn-all-off {{ background-color: #475569; color: white; }}
.btn-wifi-toggle {{ width: 100%; margin-top: 12px; background: rgba(56,189,248,0.12); color: #38bdf8; border: 1px solid rgba(56,189,248,0.3); }}
.wifi-box {{ padding: 16px; background: rgba(15,23,42,0.65); border: 1px solid rgba(255,255,255,0.1); border-radius: 14px; }}
.wifi-box h4 {{ font-size: 15px; color: #38bdf8; margin-bottom: 12px; }}
.form-group {{ margin-bottom: 12px; }}
.form-group label {{ display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 5px; }}
.input-row {{ display: flex; gap: 8px; }}
select, input[type="text"], input[type="password"] {{
  width: 100%;
  padding: 9px 11px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.15);
  background: #0f172a;
  color: var(--text-main);
  font-size: 13px;
}}
.btn-sm {{ padding: 9px 12px; font-size: 12px; border-radius: 8px; border: none; cursor: pointer; background: #334155; color: white; white-space: nowrap; }}
.btn-save {{ background: #10b981; color: #052e16; font-weight: 700; width: 100%; }}
.btn-forget {{ background: rgba(239,68,68,0.2); color: #f87171; border: 1px solid rgba(239,68,68,0.35); width: 100%; }}
.btn-change-net {{ width: 100%; background: #2563eb; color: white; margin-bottom: 10px; }}
.msg-box {{ display: none; margin-top: 12px; padding: 10px 12px; border-radius: 8px; font-size: 12px; line-height: 1.45; }}
.msg-ok {{ display: block; background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.35); }}
.msg-err {{ display: block; background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.35); }}
.msg-info {{ display: block; background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.35); }}
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

  <div id="view-welcome" class="{welcome_class}">
    <div class="welcome-box">
      <h2>Bienvenido a SmartPS</h2>
      <p>El multicontacto no está conectado a ninguna red Wi-Fi y opera en modo Punto de Acceso. Selecciona una opción:</p>
      <div class="welcome-actions">
        <button class="btn-hero btn-hero-wifi" onclick="openWifiFromWelcome()">Conectar a una Red Wi-Fi</button>
        <button class="btn-hero btn-hero-switches" onclick="showView('relays')">Acceder a los Interruptores</button>
      </div>
    </div>
  </div>

  <div id="view-relays" class="{relays_class}">
    {relays_back_btn}
    <div id="relays-list">{cards_html}</div>
    <div class="actions">
      <button class="btn btn-all-on" onclick="setAll(1)">Encender Todos</button>
      <button class="btn btn-all-off" onclick="setAll(0)">Apagar Todos</button>
    </div>
    <button class="btn btn-wifi-toggle" onclick="openWifiFromRelays()">Configurar Red Wi-Fi</button>
  </div>

  <div id="view-wifi" class="view">
    <div class="top-nav">
      <button class="btn-nav-back" onclick="handleWifiBack()">Atrás</button>
    </div>

    <div class="wifi-tabs" id="wifi-tabs" style="display: {'flex' if sta_ok else 'none'};">
      <button class="tab-btn active" id="tab-btn-info" onclick="showWifiSection('info')">Información de Red Actual</button>
      <button class="tab-btn" id="tab-btn-change" onclick="showWifiSection('change')">Cambio de Red</button>
    </div>

    <div class="wifi-box" id="wifi-section-info" style="display: {'block' if sta_ok else 'none'};">
      <h4>Información del ESP32 en la Red Actual</h4>
      <div class="info-list">
        <div class="info-row"><span class="info-label">Estado</span><span class="info-val" id="info-state">Conectado (Modo Estación)</span></div>
        <div class="info-row"><span class="info-label">Red Wi-Fi (SSID)</span><span class="info-val" id="info-ssid">{sta_ssid}</span></div>
        <div class="info-row"><span class="info-label">Dirección IP (ESP32)</span><span class="info-val" id="info-ip">{sta_ip}</span></div>
        <div class="info-row"><span class="info-label">Dominio Local</span><span class="info-val">http://{HOSTNAME}.local</span></div>
        <div class="info-row"><span class="info-label">Puerta de Enlace (Gateway)</span><span class="info-val" id="info-gw">{sta_gw}</span></div>
        <div class="info-row"><span class="info-label">Máscara de Subred</span><span class="info-val" id="info-mask">{sta_mask}</span></div>
        <div class="info-row"><span class="info-label">Servidor DNS</span><span class="info-val" id="info-dns">{sta_dns}</span></div>
        <div class="info-row"><span class="info-label">Intensidad de Señal (RSSI)</span><span class="info-val" id="info-rssi">{rssi_str}</span></div>
        <div class="info-row"><span class="info-label">Canal Wi-Fi</span><span class="info-val" id="info-chan">{chan_str}</span></div>
        <div class="info-row"><span class="info-label">Dirección MAC</span><span class="info-val" id="info-mac">{mac_str}</span></div>
      </div>

      <button class="btn btn-change-net" onclick="showWifiSection('change')">Cambiar de Red Wi-Fi</button>

      <div class="section-divider">
        <div class="form-group">
          <label>Para olvidar esta red y volver a Modo AP, ingresa la clave (SmartPS):</label>
          <input type="password" id="forget-pin" placeholder="Clave de seguridad SmartPS">
        </div>
        <button class="btn btn-forget" onclick="forgetWifi()">Olvidar Red Actual</button>
        <div id="forget-msg" class="msg-box"></div>
      </div>
    </div>

    <div class="wifi-box" id="wifi-section-change" style="display: {'none' if sta_ok else 'block'};">
      <h4>{'Cambiar a otra Red Wi-Fi (2.4 GHz)' if sta_ok else 'Conectar a Red Wi-Fi (2.4 GHz)'}</h4>
      <div class="form-group">
        <label>1. Selecciona tu red Wi-Fi:</label>
        <div class="input-row">
          <select id="ssid-select" onchange="onSelectNetwork()">
            <option value="">-- Presiona Buscar redes --</option>
          </select>
          <button class="btn-sm" onclick="scanNetworks()" id="btn-scan">Buscar</button>
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
      </div>
      <div id="wifi-msg" class="msg-box"></div>
    </div>
  </div>

  <footer>
    <p>Dominio interno: <b>http://{HOSTNAME}.local</b></p>
  </footer>
</div>

<script>
let isConnectedSta = {'true' if sta_ok else 'false'};
let previousView = isConnectedSta ? 'relays' : 'welcome';
let currentWifiSection = isConnectedSta ? 'info' : 'change';

function showView(name) {{
  document.getElementById('view-welcome').className = (name === 'welcome') ? 'view active' : 'view';
  document.getElementById('view-relays').className = (name === 'relays') ? 'view active' : 'view';
  document.getElementById('view-wifi').className = (name === 'wifi') ? 'view active' : 'view';
}}

function goBack(target) {{
  showView(target || previousView);
}}

function openWifiFromWelcome() {{
  previousView = 'welcome';
  showView('wifi');
  showWifiSection('change');
}}

function openWifiFromRelays() {{
  previousView = 'relays';
  showView('wifi');
  if (isConnectedSta) {{
    refreshNetworkInfo();
    showWifiSection('info');
  }} else {{
    showWifiSection('change');
  }}
}}

function handleWifiBack() {{
  if (isConnectedSta && currentWifiSection === 'change') {{
    showWifiSection('info');
  }} else {{
    showView(previousView);
  }}
}}

function showWifiSection(section) {{
  currentWifiSection = section;
  const infoBox = document.getElementById('wifi-section-info');
  const changeBox = document.getElementById('wifi-section-change');
  const tabInfo = document.getElementById('tab-btn-info');
  const tabChange = document.getElementById('tab-btn-change');

  if (section === 'info' && isConnectedSta) {{
    infoBox.style.display = 'block';
    changeBox.style.display = 'none';
    if (tabInfo) tabInfo.className = 'tab-btn active';
    if (tabChange) tabChange.className = 'tab-btn';
  }} else {{
    infoBox.style.display = 'none';
    changeBox.style.display = 'block';
    if (tabInfo) tabInfo.className = 'tab-btn';
    if (tabChange) tabChange.className = 'tab-btn active';
    if (document.getElementById('ssid-select').options.length <= 1) {{
      scanNetworks();
    }}
  }}
}}

function refreshNetworkInfo() {{
  fetch('/wifi/status')
    .then(r => r.json())
    .then(st => {{
      if (st.sta_connected) {{
        document.getElementById('info-ssid').textContent = st.sta_ssid || '-';
        document.getElementById('info-ip').textContent = st.sta_ip || '-';
        document.getElementById('info-gw').textContent = st.sta_gateway || '-';
        document.getElementById('info-mask').textContent = st.sta_netmask || '-';
        document.getElementById('info-dns').textContent = st.sta_dns || '-';
        document.getElementById('info-rssi').textContent = (st.sta_rssi !== null && st.sta_rssi !== undefined) ? (st.sta_rssi + ' dBm') : 'N/D';
        document.getElementById('info-chan').textContent = (st.sta_channel !== null && st.sta_channel !== undefined) ? ('Canal ' + st.sta_channel + ' (2.4 GHz)') : '2.4 GHz';
        document.getElementById('info-mac').textContent = st.mac || 'N/D';
      }}
    }})
    .catch(err => console.error(err));
}}

function toggleRelay(id, state) {{
  const val = state ? 1 : 0;
  fetch('/set?id=' + id + '&val=' + val)
    .then(response => response.json())
    .then(data => updateBadge(data.id, data.is_on))
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
  badge.className = isOn ? 'badge badge-on' : 'badge badge-off';
  badge.textContent = isOn ? 'ENCENDIDO' : 'APAGADO';
}}

function openRename(id) {{
  document.getElementById('title-row-' + id).style.display = 'none';
  document.getElementById('rename-row-' + id).classList.add('open');
  const inp = document.getElementById('rename-input-' + id);
  inp.focus();
  inp.select();
}}

function closeRename(id) {{
  document.getElementById('rename-row-' + id).classList.remove('open');
  document.getElementById('title-row-' + id).style.display = 'flex';
}}

function saveRename(id) {{
  const inp = document.getElementById('rename-input-' + id);
  const newName = inp.value.trim();
  if (!newName) return;
  fetch('/rename?id=' + id + '&name=' + encodeURIComponent(newName))
    .then(r => r.json())
    .then(res => {{
      if (res.ok) {{
        document.getElementById('name-text-' + id).textContent = res.name;
        inp.value = res.name;
        closeRename(id);
      }}
    }})
    .catch(err => console.error('Error al renombrar:', err));
}}

function showMsg(text, type, boxId) {{
  const box = document.getElementById(boxId || 'wifi-msg');
  box.className = 'msg-box ' + type;
  box.innerHTML = text;
}}

function scanNetworks() {{
  const btn = document.getElementById('btn-scan');
  const sel = document.getElementById('ssid-select');
  btn.disabled = true;
  btn.textContent = 'Buscando...';
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
      btn.textContent = 'Buscar';
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
        isConnectedSta = true;
        document.getElementById('wifi-tabs').style.display = 'flex';
        refreshNetworkInfo();
        showMsg(
          '<b>Conectado con éxito a ' + res.ssid + '</b><br>' +
          'Nueva IP asignada: <a href="http://' + res.ip + '">http://' + res.ip + '</a><br>' +
          'Dominio en tu red: <a href="http://' + res.hostname + '">http://' + res.hostname + '</a>',
          'msg-ok'
        );
        const pill = document.getElementById('net-pill');
        if (pill) {{
          pill.className = 'net-pill net-ok';
          pill.innerHTML = 'Conectado a <b>' + res.ssid + '</b> (' + res.ip + ')';
        }}
      }} else {{
        showMsg('Error: ' + res.error, 'msg-err');
      }}
    }})
    .catch(() => showMsg('Se envió la configuración. Verifica tu conexión a la red local.', 'msg-info'));
}}

function forgetWifi() {{
  const pin = document.getElementById('forget-pin').value.trim();
  if (!pin) {{
    showMsg('Ingresa la clave de seguridad (SmartPS) para olvidar la red.', 'msg-err', 'forget-msg');
    return;
  }}
  fetch('/wifi/forget?pin=' + encodeURIComponent(pin))
    .then(r => r.json())
    .then(res => {{
      if (res.ok) {{
        isConnectedSta = false;
        showMsg('Red olvidada. Punto de Acceso <b>{AP_SSID}</b> activo en http://{HOSTNAME}.local (192.168.4.1).', 'msg-ok', 'forget-msg');
        const pill = document.getElementById('net-pill');
        if (pill) {{
          pill.className = 'net-pill net-ap';
          pill.innerHTML = 'Modo AP Activo: <b>{AP_SSID}</b> (http://{HOSTNAME}.local)';
        }}
      }} else {{
        showMsg('Error: ' + res.error, 'msg-err', 'forget-msg');
      }}
    }})
    .catch(err => console.error(err));
}}
</script>
</body>
</html>"""

# ==============================================================================
# 5. SERVIDOR WEB Y ATENCIÓN DE PETICIONES
# ==============================================================================

def url_decode(val: str) -> str:
    """Decodifica caracteres especiales URL (%20, %C3%A1, +, etc.) en UTF-8."""
    if not val:
        return ""
    val = val.replace("+", " ")
    parts = val.split("%")
    if len(parts) == 1:
        return val
    byte_arr = bytearray(parts[0].encode("utf-8"))
    for item in parts[1:]:
        if len(item) >= 2:
            try:
                byte_arr.append(int(item[:2], 16))
                if len(item) > 2:
                    byte_arr.extend(item[2:].encode("utf-8"))
            except ValueError:
                byte_arr.extend(("%" + item).encode("utf-8"))
        else:
            byte_arr.extend(("%" + item).encode("utf-8"))
    try:
        return byte_arr.decode("utf-8")
    except Exception:
        return "".join(chr(b) for b in byte_arr)

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

def send_all_chunks(conn, data_bytes: bytes):
    """Envía bytes en bloques de 1024B para evitar desbordamiento de buffer TCP en MicroPython."""
    mv = memoryview(data_bytes)
    total = len(data_bytes)
    sent = 0
    while sent < total:
        chunk = mv[sent : sent + 1024]
        n = conn.send(chunk)
        if not n:
            break
        sent += n

def send_json(conn, payload_obj, status="200 OK"):
    body = json.dumps(payload_obj).encode("utf-8")
    headers = (
        f"HTTP/1.1 {status}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("utf-8")
    send_all_chunks(conn, headers)
    send_all_chunks(conn, body)

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
        conn = None
        try:
            # Procesar consultas DNS del dominio interno y tareas del WiFiManager
            wifi.tick()

            gc_counter += 1
            if gc_counter >= 50:
                gc.collect()
                gc_counter = 0

            try:
                conn, addr = s.accept()
            except OSError:
                # No hay nueva conexión HTTP en este ciclo (timeout de 50ms)
                continue

            conn.settimeout(5.0)
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
            client_ip = addr[0]

            # Extraer cabecera Host (ej. smartps.local o 192.168.4.1)
            host_header = ""
            for line in request.split('\r\n')[1:]:
                if line.lower().startswith('host:'):
                    host_header = line.split(':', 1)[1].strip()
                    break
            
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
                    print(f"[WEB] Cliente {client_ip} -> Conmutando [{relays[relay_id]['name']}]")
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
                print(f"[WEB] Cliente {client_ip} -> {'ENCENDER' if val else 'APAGAR'} TODOS")
                for r in relays:
                    set_relay(r["id"], bool(val))
                
                items = [{"id": r["id"], "is_on": r["is_on"]} for r in relays]
                send_json(conn, items)
                conn.close()
                continue

            # 4. Endpoint API: Personalizar nombre de un contacto (/rename?id=0&name=...)
            if path.startswith('/rename?'):
                params = parse_query_params(path)
                relay_id = int(params.get('id', -1))
                new_name = params.get('name', '').strip()
                if rename_relay(relay_id, new_name):
                    send_json(conn, {"ok": True, "id": relay_id, "name": relays[relay_id]["name"]})
                else:
                    send_json(conn, {"ok": False, "error": "Nombre o ID inválido."}, status="400 Bad Request")
                conn.close()
                continue

            # 5. Endpoint Wi-Fi: Escanear redes cercanas (/wifi/scan)
            if path.startswith('/wifi/scan'):
                print(f"[WEB] Cliente {client_ip} -> Escaneando redes Wi-Fi cercanas...")
                networks = wifi.scan_networks()
                send_json(conn, networks)
                conn.close()
                continue

            # 6. Endpoint Wi-Fi: Guardar y conectar a nueva red (/wifi/save?ssid=...&pass=...&pin=...)
            if path.startswith('/wifi/save?'):
                params = parse_query_params(path)
                ssid = params.get('ssid', '').strip()
                password = params.get('pass', '')
                pin = params.get('pin', '').strip()
                print(f"[WEB] Cliente {client_ip} -> Solicitud de conexión a red '{ssid}'")
                result = wifi.configure_new_network(ssid, password, pin)
                send_json(conn, result)
                conn.close()
                continue

            # 7. Endpoint Wi-Fi: Olvidar red actual y volver a modo AP (/wifi/forget?pin=...)
            if path.startswith('/wifi/forget?'):
                params = parse_query_params(path)
                pin = params.get('pin', '').strip()
                if pin != ADMIN_PIN:
                    print(f"[WEB] Cliente {client_ip} -> Intento fallido de olvidar red (Clave incorrecta)")
                    send_json(conn, {"ok": False, "error": "Clave de seguridad incorrecta."})
                else:
                    print(f"[WEB] Cliente {client_ip} -> Olvidando red Wi-Fi guardada")
                    wifi.clear_config()
                    send_json(conn, {"ok": True})
                conn.close()
                continue

            # 8. Endpoint Wi-Fi: Consultar estado actual (/wifi/status)
            if path.startswith('/wifi/status'):
                send_json(conn, get_full_net_status())
                conn.close()
                continue

            # 9. Ruta Principal (y detección de Portal Cautivo): Retornar interfaz HTML
            print(f"[WEB] Acceso a página principal desde {client_ip} (Host: {host_header or 'directo'} | Ruta: {path})")
            gc.collect()
            html_bytes = generar_html().encode('utf-8')
            response_headers = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html; charset=UTF-8\r\n"
                f"Content-Length: {len(html_bytes)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode('utf-8')
            send_all_chunks(conn, response_headers)
            send_all_chunks(conn, html_bytes)
            conn.close()

        except Exception as e:
            print(f"[WEB] Error procesando petición: {e}")
            if conn is not None:
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
