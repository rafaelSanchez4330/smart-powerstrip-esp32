"""
Multicontacto Inteligente con ESP32 y MicroPython
Proyecto Académico - Servidor Web Embebido, Gestor Wi-Fi, Dashboard de Uso y Control de Relevadores

Rutas de páginas HTML servidas por el ESP32:
- GET /              -> Pantalla de Inicio con Dashboard de Tiempo de Uso (Hoy y Promedio Semanal)
- GET /interruptores -> Pantalla de Control de Relevadores y edición de nombres
- GET /red           -> Pantalla de Información de Red Actual y Cambio de Red Wi-Fi
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

# Archivos de persistencia en memoria Flash
NAMES_FILE = 'relays_names.json'
STATS_FILE = 'usage_stats.json'

# Zona horaria para corte de día (UTC-6 México)
TZ_OFFSET_SEC = -6 * 3600

# Lógica del módulo de relevadores (True = Activo en Bajo 0V, False = Activo en Alto 3.3V)
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
# 2. RELOJ, INICIALIZACIÓN DE HARDWARE Y ESTADÍSTICAS DE USO
# ==============================================================================

ntp_synced = False

def sync_ntp_time():
    """Intenta sincronizar la hora real por NTP cuando hay conexión Wi-Fi."""
    global ntp_synced
    if ntp_synced:
        return
    try:
        import ntptime
        ntptime.timeout = 2
        ntptime.settime()
        ntp_synced = True
        print("[Reloj] Hora sincronizada mediante NTP.")
    except Exception:
        pass

def get_current_day_key() -> str:
    """Devuelve identificador de fecha 'YYYY-MM-DD' para agrupar estadísticas por día."""
    t = time.localtime(time.time() + TZ_OFFSET_SEC)
    return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"

def load_custom_names() -> dict:
    try:
        with open(NAMES_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

def save_custom_names():
    try:
        data = {str(r["id"]): r["name"] for r in relays}
        with open(NAMES_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error al guardar nombres: {e}")

def get_physical_value(is_on: bool) -> int:
    if RELAY_ACTIVE_LOW:
        return 0 if is_on else 1
    else:
        return 1 if is_on else 0

saved_names = load_custom_names()
relays = []
for config in RELAYS_CONFIG:
    pin_obj = Pin(config["pin"], Pin.OUT)
    pin_obj.value(get_physical_value(False))
    custom_name = saved_names.get(str(config["id"]), config["name"])
    
    relays.append({
        "id": config["id"],
        "name": custom_name,
        "pin_num": config["pin"],
        "pin_obj": pin_obj,
        "is_on": False,
        "on_since": None,
    })

def _empty_day_dict() -> dict:
    return {str(r["id"]): 0 for r in relays}

def load_usage_stats() -> dict:
    """Carga las estadísticas de tiempo de uso diario e historial semanal."""
    day_key = get_current_day_key()
    default_stats = {
        "current_day": day_key,
        "today_sec": _empty_day_dict(),
        "today_toggles": _empty_day_dict(),
        "history": [],  # Lista de hasta 6 días previos: [{"day": "YYYY-MM-DD", "sec": {"0": 120, ...}}]
    }
    try:
        with open(STATS_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, dict) and "today_sec" in data:
                for r in relays:
                    k = str(r["id"])
                    data["today_sec"].setdefault(k, 0)
                    data.setdefault("today_toggles", {}).setdefault(k, 0)
                data.setdefault("history", [])
                data.setdefault("current_day", day_key)
                return data
    except Exception:
        pass
    return default_stats

usage_stats = load_usage_stats()

def save_usage_stats():
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(usage_stats, f)
    except Exception as e:
        print(f"Error al guardar estadísticas: {e}")

def update_active_timers(save_to_disk: bool = False):
    """
    Acumula los segundos transcurridos de los relevadores que están actualmente ENCENDIDOS
    y verifica si hubo cambio de día para rotar el historial de los últimos 7 días.
    """
    now = time.time()
    day_key = get_current_day_key()

    # Si cambió el día, guardar el día concluido en el historial (máximo 6 días previos + hoy = 7 días)
    if usage_stats.get("current_day") != day_key:
        for r in relays:
            if r["is_on"] and r["on_since"] is not None:
                elapsed = max(0, int(now - r["on_since"]))
                k = str(r["id"])
                usage_stats["today_sec"][k] = usage_stats["today_sec"].get(k, 0) + elapsed
                r["on_since"] = now

        prev_day = usage_stats.get("current_day", day_key)
        usage_stats["history"].append({
            "day": prev_day,
            "sec": dict(usage_stats["today_sec"]),
        })
        if len(usage_stats["history"]) > 6:
            usage_stats["history"] = usage_stats["history"][-6:]

        usage_stats["current_day"] = day_key
        usage_stats["today_sec"] = _empty_day_dict()
        usage_stats["today_toggles"] = _empty_day_dict()
        save_to_disk = True

    # Acumular tiempo de los contactos actualmente encendidos
    for r in relays:
        if r["is_on"] and r["on_since"] is not None:
            elapsed = max(0, int(now - r["on_since"]))
            if elapsed > 0:
                k = str(r["id"])
                usage_stats["today_sec"][k] = usage_stats["today_sec"].get(k, 0) + elapsed
                r["on_since"] = now

    if save_to_disk:
        save_usage_stats()

def reset_usage_stats():
    """Reinicia a cero las estadísticas del día y el historial semanal."""
    now = time.time()
    usage_stats["current_day"] = get_current_day_key()
    usage_stats["today_sec"] = _empty_day_dict()
    usage_stats["today_toggles"] = _empty_day_dict()
    usage_stats["history"] = []
    for r in relays:
        if r["is_on"]:
            r["on_since"] = now
        else:
            r["on_since"] = None
    save_usage_stats()
    print("[Stats] Estadísticas de tiempo de uso reiniciadas.")

def set_relay(relay_id: int, state: bool):
    """Enciende (True) o apaga (False) el relevador indicado y registra su tiempo de uso."""
    if 0 <= relay_id < len(relays):
        r = relays[relay_id]
        was_on = r["is_on"]
        now = time.time()
        k = str(relay_id)

        update_active_timers(save_to_disk=False)

        if state and not was_on:
            r["on_since"] = now
            usage_stats["today_toggles"][k] = usage_stats["today_toggles"].get(k, 0) + 1
        elif not state and was_on:
            if r["on_since"] is not None:
                elapsed = max(0, int(now - r["on_since"]))
                usage_stats["today_sec"][k] = usage_stats["today_sec"].get(k, 0) + elapsed
            r["on_since"] = None

        r["is_on"] = state
        r["pin_obj"].value(get_physical_value(state))
        save_usage_stats()
        print(f"[{r['name']}] -> {'ENCENDIDO' if state else 'APAGADO'}")

def rename_relay(relay_id: int, new_name: str) -> bool:
    """Cambia y guarda el nombre personalizado de un contacto."""
    clean_name = new_name.strip()
    if 0 <= relay_id < len(relays) and clean_name:
        relays[relay_id]["name"] = clean_name[:32]
        save_custom_names()
        print(f"[Contacto {relay_id + 1}] renombrado a: '{relays[relay_id]['name']}'")
        return True
    return False

def get_relays_state_with_stats() -> list:
    """Devuelve la lista de contactos con su estado, tiempo de hoy y promedio semanal."""
    update_active_timers(save_to_disk=False)
    history = usage_stats.get("history", [])
    days_count = len(history) + 1  # Días registrados en la ventana de hasta 7 días (mínimo 1: hoy)

    items = []
    for r in relays:
        k = str(r["id"])
        today_s = int(usage_stats["today_sec"].get(k, 0))
        hist_s = sum(int(day_entry.get("sec", {}).get(k, 0)) for day_entry in history)
        week_total_s = hist_s + today_s
        week_avg_s = int(round(week_total_s / days_count))
        toggles = int(usage_stats.get("today_toggles", {}).get(k, 0))

        items.append({
            "id": r["id"],
            "name": r["name"],
            "pin": r["pin_num"],
            "is_on": r["is_on"],
            "today_sec": today_s,
            "week_avg_sec": week_avg_s,
            "week_total_sec": week_total_s,
            "toggles_today": toggles,
            "days_recorded": days_count,
        })
    return items

def format_duration_py(sec: int) -> str:
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"

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
    """Obtiene el estado de red de forma segura."""
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
# 4. PLANTILLAS WEB SEPARADAS POR RUTA (/, /interruptores, /red)
# ==============================================================================

def html_escape(text) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

BASE_CSS = """
:root {
  --bg-color: #0f172a;
  --card-bg: #1e293b;
  --text-main: #f8fafc;
  --text-muted: #94a3b8;
  --switch-bg: #334155;
  --switch-active: #3b82f6;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background-color: var(--bg-color);
  color: var(--text-main);
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  padding: 20px;
}
.container {
  width: 100%;
  max-width: 500px;
  background: var(--card-bg);
  border-radius: 20px;
  padding: 24px 20px;
  box-shadow: 0 20px 40px rgba(0,0,0,0.4);
  border: 1px solid rgba(255,255,255,0.08);
}
header {
  text-align: center;
  margin-bottom: 16px;
  border-bottom: 1px solid rgba(255,255,255,0.1);
  padding-bottom: 14px;
}
header h1 { font-size: 22px; font-weight: 700; color: #38bdf8; }
header p { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
.net-pill {
  display: inline-block;
  margin-top: 10px;
  font-size: 12px;
  padding: 5px 12px;
  border-radius: 20px;
}
.net-ok { background: rgba(16,185,129,0.14); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }
.net-ap { background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.35); }
.top-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.btn-nav-back, .btn-nav-link {
  display: inline-block;
  text-decoration: none;
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(255,255,255,0.16);
  color: var(--text-main);
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.btn-nav-link {
  color: #38bdf8;
  border-color: rgba(56,189,248,0.3);
  background: rgba(56,189,248,0.1);
}
.btn-nav-back:hover, .btn-nav-link:hover {
  background: rgba(255,255,255,0.14);
}
.info-list {
  background: rgba(15,23,42,0.55);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 6px 14px;
  margin-bottom: 14px;
}
.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 9px 0;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  font-size: 13px;
}
.info-row:last-child { border-bottom: none; }
.info-label { color: var(--text-muted); font-size: 12px; }
.info-val { color: var(--text-main); font-weight: 600; text-align: right; }
.menu-actions { display: flex; gap: 10px; margin-bottom: 18px; }
.btn-hero {
  flex: 1;
  display: block;
  text-align: center;
  text-decoration: none;
  padding: 12px 10px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  border: none;
}
.btn-hero-primary { background: linear-gradient(135deg, #2563eb, #0284c7); color: white; }
.btn-hero-secondary {
  background: rgba(255,255,255,0.06);
  color: var(--text-main);
  border: 1px solid rgba(255,255,255,0.16);
}
.badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 10px;
  text-transform: uppercase;
}
.badge-on { background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }
.badge-off { background: rgba(100,116,139,0.15); color: #94a3b8; border: 1px solid rgba(100,116,139,0.3); }
footer { text-align: center; margin-top: 16px; font-size: 11px; color: var(--text-muted); }
a { color: #38bdf8; }
"""

def _build_status_pill(net_status: dict) -> str:
    if net_status.get("sta_connected"):
        ssid = html_escape(net_status.get("sta_ssid", ""))
        ip = html_escape(net_status.get("sta_ip", ""))
        return f'<div class="net-pill net-ok" id="net-pill">Conectado a <b>{ssid}</b> ({ip})</div>'
    return f'<div class="net-pill net-ap" id="net-pill">Modo AP Activo: <b>{AP_SSID}</b> (http://{HOSTNAME}.local)</div>'


# ------------------------------------------------------------------------------
# PÁGINA 1: PANTALLA DE INICIO CON DASHBOARD DE TIEMPO DE USO (Ruta: GET /)
# ------------------------------------------------------------------------------
def generar_html_inicio() -> str:
    net_status = get_full_net_status()
    status_pill = _build_status_pill(net_status)
    stats_list = get_relays_state_with_stats()

    encendidos = sum(1 for r in stats_list if r["is_on"])
    total_today_sec = sum(r["today_sec"] for r in stats_list)
    total_week_avg_sec = sum(r["week_avg_sec"] for r in stats_list)
    max_sec = max([r["today_sec"] for r in stats_list] + [r["week_avg_sec"] for r in stats_list] + [60])

    dash_cards = ""
    for r in stats_list:
        rid = r["id"]
        safe_name = html_escape(r["name"])
        badge_class = "badge-on" if r["is_on"] else "badge-off"
        badge_text = "ENCENDIDO" if r["is_on"] else "APAGADO"
        pct_today = min(100, int((r["today_sec"] * 100) / max_sec)) if max_sec > 0 else 0
        pct_week = min(100, int((r["week_avg_sec"] * 100) / max_sec)) if max_sec > 0 else 0

        dash_cards += (
            f'<div class="stat-card">'
            f'<div class="stat-head">'
            f'<span class="stat-name" id="st-name-{rid}">{safe_name}</span>'
            f'<span class="badge {badge_class}" id="st-badge-{rid}">{badge_text}</span>'
            f'</div>'
            f'<div class="bar-group">'
            f'<div class="bar-label"><span>Tiempo hoy</span><b id="st-today-{rid}">{format_duration_py(r["today_sec"])}</b></div>'
            f'<div class="bar-track"><div class="bar-fill bar-today" id="st-bar-today-{rid}" style="width:{pct_today}%"></div></div>'
            f'</div>'
            f'<div class="bar-group">'
            f'<div class="bar-label"><span>Promedio diario (semana)</span><b id="st-week-{rid}">{format_duration_py(r["week_avg_sec"])}</b></div>'
            f'<div class="bar-track"><div class="bar-fill bar-week" id="st-bar-week-{rid}" style="width:{pct_week}%"></div></div>'
            f'</div>'
            f'<div class="stat-foot">Activaciones hoy: <b id="st-tog-{rid}">{r["toggles_today"]}</b></div>'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Inicio y Dashboard | SmartPS</title>
<style>
{BASE_CSS}
.section-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}}
.section-title {{ font-size: 14px; color: #38bdf8; font-weight: 700; }}
.btn-reset-stats {{
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.12);
  color: var(--text-muted);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
}}
.btn-reset-stats:hover {{ color: white; border-color: #f87171; }}
.kpi-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 16px;
}}
.kpi-card {{
  background: rgba(15,23,42,0.6);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 10px 8px;
  text-align: center;
}}
.kpi-label {{ font-size: 11px; color: var(--text-muted); margin-bottom: 4px; display: block; }}
.kpi-val {{ font-size: 14px; font-weight: 700; color: var(--text-main); }}
.stat-card {{
  background: rgba(15,23,42,0.55);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 10px;
}}
.stat-head {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}}
.stat-name {{ font-size: 14px; font-weight: 600; color: var(--text-main); }}
.bar-group {{ margin-bottom: 6px; }}
.bar-label {{
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 3px;
}}
.bar-label b {{ color: var(--text-main); font-weight: 600; }}
.bar-track {{
  width: 100%;
  height: 7px;
  background: rgba(255,255,255,0.07);
  border-radius: 4px;
  overflow: hidden;
}}
.bar-fill {{
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
}}
.bar-today {{ background: linear-gradient(90deg, #3b82f6, #38bdf8); }}
.bar-week {{ background: linear-gradient(90deg, #10b981, #34d399); }}
.stat-foot {{ font-size: 11px; color: var(--text-muted); margin-top: 4px; text-align: right; }}
.stat-foot b {{ color: var(--text-main); }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Multicontacto Inteligente</h1>
    <p>SmartPS | Pantalla de Inicio</p>
    {status_pill}
  </header>

  <div class="menu-actions">
    <a href="/interruptores" class="btn-hero btn-hero-primary">Interruptores</a>
    <a href="/red" class="btn-hero btn-hero-secondary">Red Wi-Fi</a>
  </div>

  <div class="section-header">
    <span class="section-title">Dashboard de Tiempo de Uso</span>
    <button class="btn-reset-stats" onclick="resetStats()">Reiniciar Contadores</button>
  </div>

  <div class="kpi-grid">
    <div class="kpi-card">
      <span class="kpi-label">Encendidos</span>
      <span class="kpi-val" id="kpi-active">{encendidos} de {len(stats_list)}</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Total Hoy</span>
      <span class="kpi-val" id="kpi-today">{format_duration_py(total_today_sec)}</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Prom. Semanal</span>
      <span class="kpi-val" id="kpi-week">{format_duration_py(total_week_avg_sec)}</span>
    </div>
  </div>

  <div id="stats-list">
    {dash_cards}
  </div>

  <footer>
    <p>Dominio interno: <b>http://{HOSTNAME}.local</b></p>
  </footer>
</div>

<script>
function fmtDur(sec) {{
  sec = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = n => (n < 10 ? '0' + n : '' + n);
  if (h > 0) return h + 'h ' + pad(m) + 'm ' + pad(s) + 's';
  if (m > 0) return m + 'm ' + pad(s) + 's';
  return s + 's';
}}

function syncDashboard() {{
  if (document.hidden) return;
  fetch('/relays/state')
    .then(r => r.json())
    .then(data => {{
      let onCount = 0;
      let sumToday = 0;
      let sumWeek = 0;
      let maxVal = 60;

      data.forEach(r => {{
        if (r.is_on) onCount++;
        sumToday += (r.today_sec || 0);
        sumWeek += (r.week_avg_sec || 0);
        if (r.today_sec > maxVal) maxVal = r.today_sec;
        if (r.week_avg_sec > maxVal) maxVal = r.week_avg_sec;
      }});

      document.getElementById('kpi-active').textContent = onCount + ' de ' + data.length;
      document.getElementById('kpi-today').textContent = fmtDur(sumToday);
      document.getElementById('kpi-week').textContent = fmtDur(sumWeek);

      data.forEach(r => {{
        const b = document.getElementById('st-badge-' + r.id);
        if (b) {{
          b.className = r.is_on ? 'badge badge-on' : 'badge badge-off';
          b.textContent = r.is_on ? 'ENCENDIDO' : 'APAGADO';
        }}
        const n = document.getElementById('st-name-' + r.id);
        if (n && r.name) n.textContent = r.name;

        const tEl = document.getElementById('st-today-' + r.id);
        if (tEl) tEl.textContent = fmtDur(r.today_sec);

        const wEl = document.getElementById('st-week-' + r.id);
        if (wEl) wEl.textContent = fmtDur(r.week_avg_sec);

        const togEl = document.getElementById('st-tog-' + r.id);
        if (togEl) togEl.textContent = r.toggles_today || 0;

        const pctT = Math.min(100, Math.floor(((r.today_sec || 0) * 100) / maxVal));
        const pctW = Math.min(100, Math.floor(((r.week_avg_sec || 0) * 100) / maxVal));
        const bt = document.getElementById('st-bar-today-' + r.id);
        const bw = document.getElementById('st-bar-week-' + r.id);
        if (bt) bt.style.width = pctT + '%';
        if (bw) bw.style.width = pctW + '%';
      }});
    }})
    .catch(() => {{}});
}}

function resetStats() {{
  fetch('/stats/reset')
    .then(r => r.json())
    .then(() => syncDashboard())
    .catch(() => {{}});
}}

setInterval(syncDashboard, 1500);
</script>
</body>
</html>"""


# ------------------------------------------------------------------------------
# PÁGINA 2: CONTROL DE INTERRUPTORES (Ruta: GET /interruptores)
# ------------------------------------------------------------------------------
def generar_html_interruptores() -> str:
    net_status = get_full_net_status()
    status_pill = _build_status_pill(net_status)

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
<title>Interruptores | SmartPS</title>
<style>
{BASE_CSS}
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
.rename-row input {{
  width: 100%;
  padding: 6px 9px;
  font-size: 13px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.15);
  background: #0f172a;
  color: var(--text-main);
}}
.btn-mini {{ border: none; border-radius: 6px; padding: 6px 9px; font-size: 12px; font-weight: 600; cursor: pointer; }}
.btn-mini-ok {{ background: #10b981; color: #052e16; }}
.btn-mini-cancel {{ background: #475569; color: white; }}
.pin-info {{ font-size: 11px; color: var(--text-muted); margin-left: 8px; }}
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
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Multicontacto Inteligente</h1>
    <p>Control de Interruptores</p>
    {status_pill}
  </header>

  <div class="top-nav">
    <a href="/" class="btn-nav-back">Atrás (Inicio)</a>
    <a href="/red" class="btn-nav-link">Red Wi-Fi</a>
  </div>

  <div id="relays-list">{cards_html}</div>

  <div class="actions">
    <button class="btn btn-all-on" onclick="setAll(1)">Encender Todos</button>
    <button class="btn btn-all-off" onclick="setAll(0)">Apagar Todos</button>
  </div>

  <footer>
    <p>Dominio interno: <b>http://{HOSTNAME}.local</b></p>
  </footer>
</div>

<script>
function toggleRelay(id, state) {{
  const val = state ? 1 : 0;
  fetch('/set?id=' + id + '&val=' + val)
    .then(r => r.json())
    .then(d => updateBadge(d.id, d.is_on))
    .catch(err => console.error(err));
}}

function setAll(val) {{
  fetch('/set_all?val=' + val)
    .then(r => r.json())
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
    .catch(err => console.error(err));
}}

function syncRelaysState() {{
  if (document.hidden) return;
  fetch('/relays/state')
    .then(r => r.json())
    .then(data => {{
      data.forEach(r => {{
        const sw = document.getElementById('switch-' + r.id);
        if (sw && sw.checked !== r.is_on) sw.checked = r.is_on;
        updateBadge(r.id, r.is_on);
        const row = document.getElementById('rename-row-' + r.id);
        const isEditing = row && row.classList.contains('open');
        const nameEl = document.getElementById('name-text-' + r.id);
        if (nameEl && !isEditing && r.name && nameEl.textContent !== r.name) {{
          nameEl.textContent = r.name;
          const inp = document.getElementById('rename-input-' + r.id);
          if (inp) inp.value = r.name;
        }}
      }});
    }})
    .catch(() => {{}});
}}
setInterval(syncRelaysState, 1500);
</script>
</body>
</html>"""


# ------------------------------------------------------------------------------
# PÁGINA 3: INFORMACIÓN Y CONFIGURACIÓN DE RED WI-FI (Ruta: GET /red)
# ------------------------------------------------------------------------------
def generar_html_red() -> str:
    net_status = get_full_net_status()
    sta_ok = bool(net_status.get("sta_connected"))
    status_pill = _build_status_pill(net_status)

    sta_ssid = html_escape(net_status.get("sta_ssid", "-"))
    sta_ip = html_escape(net_status.get("sta_ip", "-"))
    sta_gw = html_escape(net_status.get("sta_gateway", "-"))
    sta_mask = html_escape(net_status.get("sta_netmask", "-"))
    sta_dns = html_escape(net_status.get("sta_dns", "-"))
    rssi_val = net_status.get("sta_rssi")
    chan_val = net_status.get("sta_channel")
    rssi_str = f"{rssi_val} dBm" if rssi_val is not None else "N/D"
    chan_str = f"Canal {chan_val} (2.4 GHz)" if chan_val is not None else "2.4 GHz"
    mac_str = html_escape(net_status.get("mac") or "N/D")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Red Wi-Fi | SmartPS</title>
<style>
{BASE_CSS}
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
.btn {{ padding: 11px 12px; border: none; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer; }}
.btn-sm {{ padding: 9px 12px; font-size: 12px; border-radius: 8px; border: none; cursor: pointer; background: #334155; color: white; white-space: nowrap; }}
.btn-save {{ background: #10b981; color: #052e16; font-weight: 700; width: 100%; margin-top: 6px; }}
.btn-forget {{ background: rgba(239,68,68,0.2); color: #f87171; border: 1px solid rgba(239,68,68,0.35); width: 100%; }}
.btn-change-net {{ width: 100%; background: #2563eb; color: white; margin-bottom: 10px; }}
.section-divider {{ margin-top: 16px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,0.08); }}
.msg-box {{ display: none; margin-top: 12px; padding: 10px 12px; border-radius: 8px; font-size: 12px; line-height: 1.45; }}
.msg-ok {{ display: block; background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.35); }}
.msg-err {{ display: block; background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.35); }}
.msg-info {{ display: block; background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.35); }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Multicontacto Inteligente</h1>
    <p>Gestión de Red Wi-Fi</p>
    {status_pill}
  </header>

  <div class="top-nav">
    <button class="btn-nav-back" onclick="handleBack()">Atrás</button>
    <a href="/interruptores" class="btn-nav-link">Interruptores</a>
  </div>

  <div class="wifi-tabs" id="wifi-tabs" style="display: {'flex' if sta_ok else 'none'};">
    <button class="tab-btn active" id="tab-btn-info" onclick="showSection('info')">Información de Red Actual</button>
    <button class="tab-btn" id="tab-btn-change" onclick="showSection('change')">Cambio de Red</button>
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

    <button class="btn btn-change-net" onclick="showSection('change')">Cambiar de Red Wi-Fi</button>

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
    <button class="btn btn-save" onclick="saveWifi()">Guardar y Conectar</button>
    <div id="wifi-msg" class="msg-box"></div>
  </div>

  <footer>
    <p>Dominio interno: <b>http://{HOSTNAME}.local</b></p>
  </footer>
</div>

<script>
let isConnectedSta = {'true' if sta_ok else 'false'};
let currentSection = isConnectedSta ? 'info' : 'change';

function handleBack() {{
  if (isConnectedSta && currentSection === 'change') {{
    showSection('info');
  }} else {{
    window.location.href = '/';
  }}
}}

function showSection(section) {{
  currentSection = section;
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
    .catch(() => {{}});
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
    .catch(() => {{}});
}}

if (!isConnectedSta) {{
  scanNetworks();
}}
</script>
</body>
</html>"""


# ==============================================================================
# 5. SERVIDOR WEB Y ENRUTADOR DE PÁGINAS Y API
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
    """Envía bytes en bloques de 1024B para evitar desbordamiento de buffer TCP."""
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

def send_html(conn, html_str: str):
    gc.collect()
    html_bytes = html_str.encode("utf-8")
    headers = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html; charset=UTF-8\r\n"
        f"Content-Length: {len(html_bytes)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("utf-8")
    send_all_chunks(conn, headers)
    send_all_chunks(conn, html_bytes)

def iniciar_servidor():
    if wifi.sta.isconnected():
        sync_ntp_time()
        usage_stats["current_day"] = get_current_day_key()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', 80))
    s.listen(5)
    s.settimeout(0.05)
    print(f"Servidor web activo en http://{HOSTNAME}.local (Puerto 80)...\n")

    gc_counter = 0
    last_stats_flush = time.time()

    while True:
        conn = None
        try:
            wifi.tick()

            now = time.time()
            if now - last_stats_flush >= 60:
                last_stats_flush = now
                update_active_timers(save_to_disk=True)

            gc_counter += 1
            if gc_counter >= 50:
                gc.collect()
                gc_counter = 0

            try:
                conn, addr = s.accept()
            except OSError:
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
            clean_route = path.split('?')[0]
            client_ip = addr[0]

            host_header = ""
            for line in request.split('\r\n')[1:]:
                if line.lower().startswith('host:'):
                    host_header = line.split(':', 1)[1].strip()
                    break
            
            # 1. Ignorar solicitudes de favicon
            if clean_route == '/favicon.ico':
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
                
                send_json(conn, get_relays_state_with_stats())
                conn.close()
                continue

            # 4. Endpoint API: Sincronización de estado y estadísticas en tiempo real (/relays/state)
            if clean_route == '/relays/state':
                send_json(conn, get_relays_state_with_stats())
                conn.close()
                continue

            # 4B. Endpoint API: Reiniciar estadísticas de uso (/stats/reset)
            if clean_route == '/stats/reset':
                print(f"[WEB] Cliente {client_ip} -> Reiniciando estadísticas de uso")
                reset_usage_stats()
                send_json(conn, {"ok": True})
                conn.close()
                continue

            # 5. Endpoint API: Personalizar nombre de un contacto (/rename?id=0&name=...)
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

            # 6. Endpoint Wi-Fi: Escanear redes cercanas (/wifi/scan)
            if clean_route == '/wifi/scan':
                print(f"[WEB] Cliente {client_ip} -> Escaneando redes Wi-Fi cercanas...")
                networks = wifi.scan_networks()
                send_json(conn, networks)
                conn.close()
                continue

            # 7. Endpoint Wi-Fi: Guardar y conectar a nueva red (/wifi/save?ssid=...&pass=...&pin=...)
            if path.startswith('/wifi/save?'):
                params = parse_query_params(path)
                ssid = params.get('ssid', '').strip()
                password = params.get('pass', '')
                pin = params.get('pin', '').strip()
                print(f"[WEB] Cliente {client_ip} -> Solicitud de conexión a red '{ssid}'")
                result = wifi.configure_new_network(ssid, password, pin)
                if result.get("ok"):
                    sync_ntp_time()
                send_json(conn, result)
                conn.close()
                continue

            # 8. Endpoint Wi-Fi: Olvidar red actual y volver a modo AP (/wifi/forget?pin=...)
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

            # 9. Endpoint Wi-Fi: Consultar estado actual (/wifi/status)
            if clean_route == '/wifi/status':
                send_json(conn, get_full_net_status())
                conn.close()
                continue

            # 10. RUTAS DE PÁGINAS HTML SEPARADAS
            if clean_route == '/interruptores':
                print(f"[WEB] Cliente {client_ip} -> Página de Interruptores (/interruptores)")
                send_html(conn, generar_html_interruptores())
                conn.close()
                continue

            if clean_route == '/red':
                print(f"[WEB] Cliente {client_ip} -> Página de Red Wi-Fi (/red)")
                send_html(conn, generar_html_red())
                conn.close()
                continue

            # Ruta Principal '/' (y cualquier ruta de Portal Cautivo): Pantalla de Inicio con Dashboard
            print(f"[WEB] Cliente {client_ip} -> Pantalla de Inicio y Dashboard ({clean_route} | Host: {host_header or 'directo'})")
            send_html(conn, generar_html_inicio())
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
