# Multicontacto Inteligente con ESP32 y MicroPython
> **Proyecto Académico de Sistemas Embebidos e Internet de las Cosas (IoT)**

Este repositorio contiene el diseño, código fuente y documentación técnica para la construcción de un **multicontacto eléctrico inteligente** controlado mediante un microcontrolador **ESP32** programado en **MicroPython**. El sistema integra un servidor web embebido que permite monitorear y conmutar individualmente el suministro de corriente de cada contacto eléctrico a través de cualquier dispositivo con navegador web (smartphone, tablet o PC) conectado a la red local.

---

## 📋 Tabla de Contenidos

1. [Características Principales](#-características-principales)
2. [Arquitectura del Sistema](#-arquitectura-del-sistema)
3. [Requisitos Previos](#-requisitos-previos)
4. [Guía de Instalación del Firmware (MicroPython)](#-guía-de-instalación-del-firmware-micropython)
   - [Opción A: Instalación mediante esptool (Línea de comandos)](#opción-a-instalación-mediante-esptool-línea-de-comandos)
   - [Opción B: Instalación gráfica con Thonny IDE (Recomendada)](#opción-b-instalación-gráfica-con-thonny-ide-recomendada)
5. [Carga y Configuración del Código](#-carga-y-configuración-del-código)
6. [Diagrama de Conexiones y Pinout](#-diagrama-de-conexiones-y-pinout)
7. [Instrucciones de Uso de la Interfaz Web](#-instrucciones-de-uso-de-la-interfaz-web)
8. [Medidas de Seguridad Eléctrica](#-medidas-de-seguridad-eléctrica)
9. [Lista de Materiales (BOM)](#-lista-de-materiales-bom)

---

## 🚀 Características Principales

* **Servidor Web Embebido Autónomo:** No requiere conexión a servicios en la nube externos ni pasarelas adicionales; opera dentro de la red de área local (LAN).
* **Control Multicanal:** Conmutación independiente de relevadores (4 canales por defecto, escalable a más).
* **Interfaz Web Asíncrona (SPA):** Tablero de control responsivo con interruptores tipo switch (*toggle sliders*). Utiliza peticiones asíncronas (`fetch API`) para actualizar el estado instantáneamente sin recargar la página.
* **Portal de Configuración Wi-Fi ("Wi-Fi Manager"):** Permite escanear redes Wi-Fi cercanas e ingresar las credenciales desde el navegador web, guardándolas de forma permanente en la memoria Flash (`wifi_config.json`).
* **Dominio Interno y Servidor DNS Local:** Accesible mediante **`http://smartps.local`** tanto en modo Punto de Acceso (mediante un micro-servidor DNS en el puerto UDP 53) como en la red local (mDNS/DHCP hostname).
* **Modo Punto de Acceso (AP) Protegido:** Si no hay red configurada o falla la conexión, el ESP32 levanta su propia red Wi-Fi (`SmartPS`, contraseña `SmartPS123`) y solicita la clave de seguridad (`SmartPS`) para modificar la configuración de red.
* **Inicialización Segura de Pines:** Previene pulsos o encendidos involuntarios durante el arranque del microcontrolador.
* **Gestión de Recursos en MicroPython:** Manejo de excepciones, timeouts en sockets y recolección forzada de basura (`gc.collect()`) para garantizar estabilidad continua.

---

## 🏛 Arquitectura del Sistema

```
[ Dispositivo Móvil / PC ]
         │ (HTTP / Navegador Web)
         ▼
[ Red Wi-Fi Local (Router) / AP ]
         │
         ▼
┌────────────────────────────────────────────────────────┐
│                      ESP32                             │
│  - Firmware: MicroPython v1.20+                        │
│  - Socket Server HTTP en puerto 80                    │
│  - Lógica de control GPIOs (Pines 16, 17, 18, 19)      │
└────────────────────────────────────────────────────────┘
         │ (Señales lógicas 3.3V - Active LOW)
         ▼
┌────────────────────────────────────────────────────────┐
│     Módulo de Relevadores de 5V (Optoacoplado)         │
│  - Aislamiento galvánico entre control y potencia      │
└────────────────────────────────────────────────────────┘
         │ (Conmutación mecánica de Fase - 110V/220V AC)
         ▼
[ Contactos Eléctricos 1, 2, 3 y 4 ] ──► [ Cargas / Electrodomésticos ]
```

---

## 🧰 Requisitos Previos

### Hardware
* 1x Placa de desarrollo **ESP32** (ESP-WROOM-32 / DevKit V1).
* 1x **Módulo de 4 Relevadores** de 5V con optoacoplador (10A @ 125/250VAC).
* 1x Fuente de alimentación regulada de 5V DC (mínimo 1.5A) o cargador USB.
* Tomas de corriente / contactos eléctricos (NEMA 5-15R o estándar local).
* Cable USB a Micro-USB/Tipo-C con soporte de datos.
* Cable eléctrico calibre 14 AWG, clavija de uso rudo y caja envolvente plástica.
*(Consulta la lista detallada en [docs/lista_de_materiales.md](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/docs/lista_de_materiales.md))*.

### Software
* **Drivers USB a UART:** Según el chip conversor de tu placa:
  * Driver [Silicon Labs CP210x](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers)
  * Driver [WCH CH340 / CH341](http://www.wch-ic.com/downloads/CH341SER_EXE.html)
* **Python 3.8+** instalado en tu sistema operativo.
* Herramienta **esptool** (`pip install esptool`).
* **Thonny IDE** (recomendado para desarrollo y carga en MicroPython): [Descargar Thonny](https://thonny.org/).
* Archivo binario del **Firmware MicroPython para ESP32** (descargar la versión oficial más reciente para placas genéricas desde [micropython.org/download/ESP32_GENERIC/](https://micropython.org/download/ESP32_GENERIC/)).

---

## ⚡ Guía de Instalación del Firmware (MicroPython)

### Opción A: Instalación mediante esptool (Línea de comandos)

1. **Identificar el puerto COM asignado:**
   Conecta la placa ESP32 a la computadora mediante el cable USB.
   * En Windows: Abre el *Administrador de dispositivos* y expande la sección **Puertos (COM y LPT)** (ejemplo: `COM3`, `COM4`).
   * En Linux/macOS: Ejecuta `ls /dev/tty*` (usualmente `/dev/ttyUSB0` o `/dev/cu.usbserial-*`).

2. **Instalar esptool:**
   Abre una terminal y ejecuta:
   ```bash
   pip install esptool
   ```

3. **Borrar la memoria Flash del ESP32:**
   > [!TIP]
   > Si el comando se queda esperando con el mensaje `Connecting........_____.....`, mantén presionado el botón **BOOT** de la placa ESP32 durante 2 segundos para forzar el modo de descarga.
   
   ```bash
   esptool.py --chip esp32 --port COM3 erase_flash
   ```
   *(Reemplaza `COM3` por el puerto correspondiente a tu placa).*

4. **Flashear la imagen de MicroPython:**
   Escribe el firmware a partir de la dirección base `0x1000`:
   ```bash
   esptool.py --chip esp32 --port COM3 --baud 460800 write_flash -z 0x1000 ruta/al/archivo/ESP32_GENERIC-xxxx.bin
   ```

---

### Opción B: Instalación gráfica con Thonny IDE (Recomendada)

1. Abre **Thonny IDE**.
2. Ve al menú superior: **Herramientas (Tools)** > **Opciones (Options)** > Pestaña **Intérprete (Interpreter)**.
3. Selecciona: **MicroPython (ESP32)**.
4. En el campo de puerto, selecciona el puerto COM de tu ESP32.
5. Haz clic en el enlace azul en la esquina inferior derecha: **Instalar o actualizar MicroPython (Install or update MicroPython)**.
6. Selecciona el puerto, busca el archivo `.bin` descargado de MicroPython y haz clic en **Instalar**.
7. Al finalizar la barra de progreso, cierra la ventana y presiona el botón físico **EN / RST** en el ESP32. La consola de Thonny mostrará el prompt interactivo de MicroPython (`>>>`).

---

## 💻 Carga y Configuración del Código

El proyecto se divide en dos módulos ubicados en la carpeta `src/`:
* [`src/wifi_manager.py`](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/src/wifi_manager.py): Gestiona la conexión Wi-Fi, el guardado persistente en `wifi_config.json`, el escaneo de redes, el Punto de Acceso (`SmartPS`) y el servidor DNS interno (`http://smartps.local`).
* [`src/main.py`](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/src/main.py): Controla los relevadores, expone el servidor HTTP y sirve la interfaz web.

### 1. Verificar Pines y Seguridad (Opcional)
No es necesario escribir las credenciales de tu red Wi-Fi en el código, ya que puedes configurarlas directamente desde el navegador web al encender el ESP32. Si deseas ajustar pines o las claves por defecto, revisa el inicio de [`src/main.py`](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/src/main.py):

```python
# Credenciales del Punto de Acceso (AP) del ESP32 y Clave de Seguridad Web
AP_SSID = 'SmartPS'
AP_PASSWORD = 'SmartPS123'   # WPA2 exige mínimo 8 caracteres
ADMIN_PIN = 'SmartPS'        # Clave solicitada en la web para cambiar el Wi-Fi
HOSTNAME = 'smartps'         # Dominio interno: http://smartps.local

# Lógica del módulo de relés:
RELAY_ACTIVE_LOW = True

# Mapeo de salidas GPIO
RELAYS_CONFIG = [
    {"id": 0, "name": "Contacto 1 (Lámpara)", "pin": 16},
    {"id": 1, "name": "Contacto 2 (Cargador)", "pin": 17},
    {"id": 2, "name": "Contacto 3 (Monitor)", "pin": 18},
    {"id": 3, "name": "Contacto 4 (Auxiliar)", "pin": 19},
]
```

### 2. Subir los archivos al ESP32

Debes subir **ambos archivos** (`wifi_manager.py` y `main.py`) a la raíz de la memoria del ESP32:

#### Mediante Thonny IDE:
1. Abre [`src/wifi_manager.py`](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/src/wifi_manager.py) en Thonny, ve a **Archivo > Guardar como... > Dispositivo MicroPython** y guárdalo en la raíz como **`wifi_manager.py`**.
2. Abre [`src/main.py`](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/src/main.py) en Thonny, ve a **Archivo > Guardar como... > Dispositivo MicroPython** y guárdalo en la raíz como **`main.py`**.
   > **¿Por qué `main.py`?** MicroPython ejecuta automáticamente `main.py` cada vez que el microcontrolador recibe energía o se reinicia.
3. Presiona el botón de reinicio (`EN / RST`) del ESP32.

#### Mediante línea de comandos (mpremote):
```bash
pip install mpremote
mpremote connect COM3 cp src/wifi_manager.py :wifi_manager.py
mpremote connect COM3 cp src/main.py :main.py
mpremote connect COM3 reset
```

---

## 🔌 Diagrama de Conexiones y Pinout

### 1. Interconexión de Baja Tensión (Control)

| ESP32 Pin | Módulo Relevadores (Entradas) | Notas |
| :---: | :---: | :--- |
| **VIN / 5V** | **VCC** (Bobinas) | Alimentación de 5V para el módulo de relés. |
| **GND** | **GND** | Masa común entre ESP32 y el módulo. |
| **GPIO 16** | **IN1** | Control del Contacto 1. |
| **GPIO 17** | **IN2** | Control del Contacto 2. |
| **GPIO 18** | **IN3** | Control del Contacto 3. |
| **GPIO 19** | **IN4** | Control del Contacto 4. |

> [!WARNING]
> **Pines Prohibidos para Salidas de Relés:**
> - **GPIOs 6 al 11:** Conectados internamente a la memoria Flash SPI integrada. Usarlos provocará el bloqueo instantáneo del ESP32.
> - **GPIOs 34, 35, 36, 39:** Son pines de **solo entrada** (no disponen de transistores de salida).
> - **GPIOs 0, 2, 12, 15:** Son pines de configuración de arranque (*strapping pins*). Conectarles relés puede impedir que el microcontrolador inicie o entre en modo programación.

---

### 2. Cableado de Potencia (Alta Tensión 110V / 220V AC)

> [!CAUTION]
> **REGLA DE ORO DE SEGURIDAD ELÉCTRICA:**
> El relevador debe interrumpir **únicamente la Fase (Línea Viva)**, nunca el cable Neutro ni la Tierra.

```
Línea Viva (Fase - Cable Negro/Café) ──[ Fusible 10A ]──┬──► [ COM 1 ]  ──( NO 1 )──► Toma 1 (Ranura Corta)
                                                        ├──► [ COM 2 ]  ──( NO 2 )──► Toma 2 (Ranura Corta)
                                                        ├──► [ COM 3 ]  ──( NO 3 )──► Toma 3 (Ranura Corta)
                                                        └──► [ COM 4 ]  ──( NO 4 )──► Toma 4 (Ranura Corta)

Neutro (Cable Blanco/Azul) ────────────( Clema WAGO común )───────────────► Todas las Tomas (Ranura Ancha)

Tierra Física (Cable Verde) ───────────( Clema WAGO común )───────────────► Todas las Tomas (Ranura U)
```

* **COM (Común):** Terminal central del relevador donde ingresa la Fase general.
* **NO (Normally Open - Normalmente Abierto):** Terminal de salida hacia la toma. Solo conducirá electricidad cuando el relevador se active desde la web.

---

## 🌐 Instrucciones de Uso y Configuración Wi-Fi

1. **Primer Encendido (Modo Punto de Acceso `SmartPS`):**
   Cuando el ESP32 se enciende por primera vez (o cuando no encuentra la red Wi-Fi guardada):
   * Levanta su propia red Wi-Fi llamada **`SmartPS`**.
   * Conéctate desde tu celular o PC usando la contraseña: **`SmartPS123`**.
   * Abre tu navegador e ingresa al dominio interno:
     ```
     http://smartps.local
     ```
     *(o directamente a la IP `http://192.168.4.1`).*

2. **Configurar el Wi-Fi de tu Casa / Escuela desde la Web:**
   * Dentro de la página web, pulsa el botón **"⚙️ Configurar Red Wi-Fi"**.
   * El ESP32 escaneará automáticamente las redes 2.4 GHz cercanas; elige la tuya de la lista.
   * Escribe la contraseña de tu Wi-Fi y la **Clave de Seguridad del Dispositivo** (**`SmartPS`**).
   * Pulsa **"Guardar y Conectar"**. El ESP32 guardará los datos en `wifi_config.json`, se conectará a tu red y te mostrará en pantalla la nueva dirección IP asignada (además de `http://smartps.local`).
   * A partir de ese momento, aunque desconectes el multicontacto de la corriente, al volver a enchufarlo se conectará automáticamente a tu Wi-Fi.

3. **Operación del Tablero de Relevadores:**
   * **Interruptor individual:** Desliza el switch de cualquier contacto para encender o apagar la corriente. El indicador cambiará instantáneamente a **ENCENDIDO** (verde) o **APAGADO** (gris).
   * **Botones maestros:** Permiten conmutar todos los contactos al mismo tiempo ("Encender Todos" / "Apagar Todos").
   * **Olvidar Red:** Si cambias de lugar o de módem, puedes borrar la red guardada desde el panel **"⚙️ Configurar Red Wi-Fi"** ingresando la clave `SmartPS`, o simplemente encenderlo donde no esté la red anterior y conectarte de nuevo a la red `SmartPS`.

---

## ⚠️ Medidas de Seguridad Eléctrica

El voltaje de la red eléctrica doméstica (110V - 240V AC) es potencialmente letal si se manipula de manera incorrecta.

1. **Desconexión Total:** Realiza todo el ensamble, apriete de tornillos y soldaduras con la clavija principal **desconectada del tomacorriente**.
2. **Aislamiento de Terminales:** Todo borne de alta tensión o empalme debe estar completamente protegido mediante tubo termorretráctil o cinta aislante de calidad. No deben quedar alambres de cobre al descubierto.
3. **Protección Térmica y de Sobrecorriente:** Instala siempre un fusible de protección de 10A en la entrada de la Fase.
4. **Carcasa Cerrada:** No operes el multicontacto abierto. Los circuitos deben quedar alojados dentro de un gabinete o caja de PVC ignífuga.
5. **Comprobación Previa:** Antes de enchufar a 110V/220V por primera vez:
   * Usa un multímetro en modo continuidad para verificar que **no exista cortocircuito** entre Fase y Neutro, ni entre Fase y Tierra.

---

## 📦 Lista de Materiales (BOM)

Para consultar la lista completa y detallada de componentes electrónicos, de potencia, consumibles y herramientas requeridas, visita el documento:
👉 **[docs/lista_de_materiales.md](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/docs/lista_de_materiales.md)**
