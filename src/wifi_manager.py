"""
Módulo Gestor de Red y Configuración Wi-Fi (wifi_manager.py)
Multicontacto Inteligente con ESP32 y MicroPython

Funciones principales:
- Almacenamiento persistente de credenciales Wi-Fi en 'wifi_config.json'.
- Escaneo de redes Wi-Fi cercanas ordenadas por intensidad de señal (RSSI).
- Modo Punto de Acceso (AP) seguro ('SmartPS' / 'SmartPS123').
- Hostname DHCP/mDNS ('smartps' -> http://smartps.local).
- Micro-servidor DNS (UDP puerto 53) para resolver dominios internos
  (ej. http://smartps.local, http://smartps.config) hacia 192.168.4.1 en modo AP.
"""

import json
import network
import socket
import time

CONFIG_FILE = "wifi_config.json"


class DNSServer:
    """
    Micro-servidor DNS en UDP puerto 53 para el modo Punto de Acceso (AP).
    Responde a cualquier consulta DNS tipo A con la IP del ESP32 (ej. 192.168.4.1),
    permitiendo usar dominios internos como http://smartps.local o http://smartps.config
    y habilitando la detección de Portal Cautivo en celulares y computadoras.
    """

    def __init__(self, ip="192.168.4.1"):
        self.ip = ip
        self.sock = None

    def start(self):
        if self.sock is not None:
            return
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("0.0.0.0", 53))
            self.sock.setblocking(False)
            print(f"[DNS] Servidor DNS interno activo en puerto 53 -> {self.ip} (http://smartps.local)")
        except Exception as e:
            print(f"[DNS] No se pudo iniciar el servidor DNS: {e}")
            self.sock = None

    def stop(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
            print("[DNS] Servidor DNS detenido.")

    def process_next(self):
        """Procesa una consulta DNS pendiente sin bloquear el ciclo principal."""
        if self.sock is None:
            return
        try:
            data, addr = self.sock.recvfrom(512)
            if len(data) < 12:
                return

            # Construir respuesta DNS estándar apuntando a self.ip
            # Header DNS: Transaction ID (2B) + Flags 0x8180 (Standard query response, No error)
            # Questions: 1, Answer RRs: 1, Authority RRs: 0, Additional RRs: 0
            tid = data[0:2]
            flags = b"\x81\x80"
            counts = data[4:6] + data[4:6] + b"\x00\x00\x00\x00"
            query_body = data[12:]

            # Puntero al nombre consultado (0xc00c), Tipo A (0x0001), Clase IN (0x0001),
            # TTL 60s (0x0000003c), Longitud 4 bytes (0x0004) + 4 octetos de IP
            ip_bytes = bytes([int(x) for x in self.ip.split(".")])
            answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + ip_bytes

            self.sock.sendto(tid + flags + counts + query_body + answer, addr)
        except OSError:
            # EAGAIN / no hay paquetes disponibles en socket no bloqueante
            pass
        except Exception:
            pass


class WiFiManager:
    def __init__(
        self,
        ap_ssid="SmartPS",
        ap_password="SmartPS123",
        admin_pin="SmartPS",
        hostname="smartps",
        default_ssid="",
        default_password="",
    ):
        self.ap_ssid = ap_ssid
        self.ap_password = ap_password
        self.admin_pin = admin_pin
        self.hostname = hostname
        self.default_ssid = default_ssid
        self.default_password = default_password

        self.sta = network.WLAN(network.STA_IF)
        self.ap = network.WLAN(network.AP_IF)
        self.dns_server = None
        self.ap_shutdown_deadline = None

    # --------------------------------------------------------------------------
    # Almacenamiento Persistente (wifi_config.json)
    # --------------------------------------------------------------------------
    def load_config(self):
        """Carga las credenciales guardadas en la memoria Flash del ESP32."""
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                ssid = data.get("ssid", "")
                password = data.get("password", "")
                if ssid:
                    return {"ssid": ssid, "password": password}
        except Exception:
            pass

        # Si no hay archivo guardado pero se definió una red por defecto válida en código
        if self.default_ssid and self.default_ssid != "TU_RED_WIFI":
            return {"ssid": self.default_ssid, "password": self.default_password}
        return None

    def save_config(self, ssid, password):
        """Guarda las credenciales Wi-Fi en 'wifi_config.json'."""
        data = {"ssid": ssid, "password": password}
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
        print(f"[WiFi] Credenciales guardadas para la red '{ssid}'.")

    def clear_config(self):
        """Elimina las credenciales guardadas y levanta el Punto de Acceso."""
        try:
            import os
            os.remove(CONFIG_FILE)
            print("[WiFi] Archivo wifi_config.json eliminado.")
        except Exception:
            pass
        try:
            self.sta.disconnect()
        except Exception:
            pass
        self.start_ap()

    # --------------------------------------------------------------------------
    # Gestión de Interfaces Wi-Fi (STA y AP)
    # --------------------------------------------------------------------------
    def _configure_hostname(self):
        """Configura el nombre de host DHCP/mDNS (ej. smartps -> http://smartps.local)."""
        try:
            self.sta.config(dhcp_hostname=self.hostname)
        except Exception:
            try:
                network.hostname(self.hostname)
            except Exception:
                pass

    def connect_sta(self, ssid, password, timeout_sec=10):
        """Intenta conectar la interfaz STA a la red Wi-Fi indicada."""
        if not ssid:
            return False, None

        self.sta.active(True)
        self._configure_hostname()

        if self.sta.isconnected():
            current_ssid = ""
            try:
                current_ssid = self.sta.config("essid")
            except Exception:
                pass
            if current_ssid == ssid:
                return True, self.sta.ifconfig()[0]
            self.sta.disconnect()
            time.sleep(0.3)

        print(f"[WiFi] Conectando a '{ssid}'...")
        try:
            self.sta.connect(ssid, password)
        except Exception as e:
            print(f"[WiFi] Error al iniciar conexión: {e}")
            return False, None

        max_ticks = int(timeout_sec * 2)
        ticks = 0
        while not self.sta.isconnected() and ticks < max_ticks:
            time.sleep(0.5)
            print(".", end="")
            ticks += 1
        print("")

        if self.sta.isconnected():
            ip = self.sta.ifconfig()[0]
            print("=" * 50)
            print(" [WiFi] Conectado exitosamente a la red local!")
            print(f" Red (SSID): {ssid}")
            print(f" Dirección IP: http://{ip}")
            print(f" Dominio local: http://{self.hostname}.local")
            print("=" * 50)
            return True, ip

        print(f"[WiFi] No se pudo conectar a '{ssid}' tras {timeout_sec}s.")
        try:
            self.sta.disconnect()
        except Exception:
            pass
        return False, None

    def start_ap(self):
        """Activa el Punto de Acceso (AP) seguro y el servidor DNS interno."""
        self.ap.active(True)
        try:
            self.ap.config(
                essid=self.ap_ssid,
                password=self.ap_password,
                authmode=network.AUTH_WPA_WPA2_PSK,
            )
        except Exception:
            # Fallback para versiones recientes de MicroPython donde authmode se ajusta automático
            self.ap.config(essid=self.ap_ssid, password=self.ap_password)

        ap_ip = self.ap.ifconfig()[0]
        print("=" * 50)
        print(f" [AP] Modo Punto de Acceso Activo: '{self.ap_ssid}'")
        print(f" Contraseña Wi-Fi: '{self.ap_password}'")
        print(f" Clave Admin Web : '{self.admin_pin}'")
        print(f" Entra desde tu navegador a: http://{self.hostname}.local")
        print(f" (o directamente a la IP:    http://{ap_ip})")
        print("=" * 50)

        if self.dns_server is None:
            self.dns_server = DNSServer(ip=ap_ip)
        self.dns_server.start()
        self.ap_shutdown_deadline = None
        return ap_ip

    def stop_ap(self):
        """Desactiva el servidor DNS y apaga el Punto de Acceso cuando ya no se requiere."""
        if self.dns_server is not None:
            self.dns_server.stop()
        try:
            self.ap.active(False)
            print("[AP] Punto de Acceso desactivado (operando en red Wi-Fi local).")
        except Exception:
            pass
        self.ap_shutdown_deadline = None

    def auto_connect(self):
        """
        Secuencia de inicio:
        1. Busca credenciales en 'wifi_config.json'.
        2. Si existen y logra conectar, apaga el AP para ahorrar energía y operar en LAN.
        3. Si no existen o falla la conexión, levanta el AP 'SmartPS' y el DNS local.
        """
        cfg = self.load_config()
        if cfg and cfg.get("ssid"):
            ok, ip = self.connect_sta(cfg["ssid"], cfg["password"], timeout_sec=10)
            if ok:
                self.stop_ap()
                return ip

        # Fallback: Levantar AP de configuración y rescate
        return self.start_ap()

    def scan_networks(self):
        """Escanea redes Wi-Fi 2.4GHz cercanas y las devuelve ordenadas por señal."""
        self.sta.active(True)
        results = []
        seen = set()
        try:
            raw_list = self.sta.scan()
            # Ordenar por RSSI descendente (mejor señal primero)
            raw_list.sort(key=lambda x: x[3], reverse=True)
            for net in raw_list:
                ssid = net[0].decode("utf-8", "ignore").strip()
                rssi = net[3]
                auth = net[4]
                if ssid and ssid not in seen:
                    seen.add(ssid)
                    results.append({
                        "ssid": ssid,
                        "rssi": rssi,
                        "secure": auth > 0,
                    })
        except Exception as e:
            print(f"[WiFi] Error al escanear redes: {e}")
        return results

    def configure_new_network(self, ssid, password, pin):
        """
        Valida la clave de seguridad ('SmartPS'), intenta conectar a la nueva red
        y, si tiene éxito, guarda en wifi_config.json y programa el apagado diferido
        del AP (en 15 segundos) para que el navegador alcance a recibir la respuesta.
        """
        if pin != self.admin_pin:
            return {
                "ok": False,
                "error": "Clave de seguridad incorrecta. Ingresa la clave del dispositivo (SmartPS).",
            }

        if not ssid:
            return {"ok": False, "error": "Debes seleccionar o escribir el nombre de la red Wi-Fi (SSID)."}

        ok, ip = self.connect_sta(ssid, password, timeout_sec=12)
        if ok:
            self.save_config(ssid, password)
            # Si el usuario estaba conectado al AP, mantener el AP encendido 15 segundos más
            # para que reciba la respuesta JSON con la nueva IP sin perder conexión abruptamente.
            if self.ap.active():
                self.ap_shutdown_deadline = time.time() + 15
            return {
                "ok": True,
                "ssid": ssid,
                "ip": ip,
                "hostname": f"{self.hostname}.local",
            }
        else:
            # Asegurar que el AP siga activo si la conexión a la nueva red falló
            if not self.ap.active():
                self.start_ap()
            return {
                "ok": False,
                "error": f"No se pudo conectar a '{ssid}'. Verifica la contraseña y que sea una red 2.4 GHz.",
            }

    def get_status(self):
        """Devuelve un diccionario con el estado actual de la conexión Wi-Fi y AP."""
        sta_connected = self.sta.isconnected()
        sta_ip = self.sta.ifconfig()[0] if sta_connected else ""
        sta_ssid = ""
        if sta_connected:
            try:
                sta_ssid = self.sta.config("essid")
            except Exception:
                cfg = self.load_config()
                sta_ssid = cfg["ssid"] if cfg else "Conectado"

        ap_active = self.ap.active()
        ap_ip = self.ap.ifconfig()[0] if ap_active else ""

        return {
            "sta_connected": sta_connected,
            "sta_ssid": sta_ssid,
            "sta_ip": sta_ip,
            "ap_active": ap_active,
            "ap_ssid": self.ap_ssid if ap_active else "",
            "ap_ip": ap_ip,
            "hostname": f"{self.hostname}.local",
        }

    def tick(self):
        """
        Se llama periódicamente desde el bucle del servidor:
        - Atiende consultas del servidor DNS si el AP está activo.
        - Apaga el AP de forma diferida tras haber configurado exitosamente una red STA.
        """
        if self.dns_server is not None and self.dns_server.sock is not None:
            self.dns_server.process_next()

        if self.ap_shutdown_deadline is not None and time.time() >= self.ap_shutdown_deadline:
            if self.sta.isconnected():
                self.stop_ap()
            else:
                self.ap_shutdown_deadline = None

