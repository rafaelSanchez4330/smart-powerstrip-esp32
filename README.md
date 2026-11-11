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
* **Modo Punto de Acceso (AP) de Respaldo:** En caso de que la red Wi-Fi no esté disponible o las credenciales fallen, el ESP32 genera su propia red Wi-Fi de rescate (`ESP32-Multicontacto`).
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

El archivo principal [`src/main.py`](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/src/main.py) contiene tanto la lógica de control como el servidor web.

### 1. Configurar Credenciales y Pines
Abre [`src/main.py`](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/src/main.py) y edita la sección inicial de configuración:

```python
# Credenciales de tu red Wi-Fi
WIFI_SSID = 'Nombre_De_Tu_Red'
WIFI_PASSWORD = 'Contraseña_De_Tu_Red'

# Lógica del módulo de relés:
# True: El relé se activa con 0 (GND) y se apaga con 1 (3.3V) -> Comportamiento estándar en módulos con optoacoplador.
# False: El relé se activa con 1 y se apaga con 0.
RELAY_ACTIVE_LOW = True

# Mapeo de salidas GPIO
RELAYS_CONFIG = [
    {"id": 0, "name": "Contacto 1 (Lámpara)", "pin": 16},
    {"id": 1, "name": "Contacto 2 (Cargador)", "pin": 17},
    {"id": 2, "name": "Contacto 3 (Monitor)", "pin": 18},
    {"id": 3, "name": "Contacto 4 (Auxiliar)", "pin": 19},
]
```

### 2. Subir el archivo al ESP32

#### Mediante Thonny IDE:
1. Abre el archivo [`src/main.py`](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/src/main.py) en Thonny.
2. Ve a **Archivo** > **Guardar como...** (Save as...).
3. Selecciona el destino: **Dispositivo MicroPython (MicroPython device)**.
4. Nómbralo obligatoriamente como **`main.py`** en la raíz del ESP32.
   > **¿Por qué `main.py`?** MicroPython ejecuta automáticamente `boot.py` (si existe) y luego `main.py` cada vez que el microcontrolador se enciende o se reinicia.
5. Presiona el botón de reinicio del ESP32 o el botón rojo "Detener/Reiniciar" en Thonny.

#### Mediante línea de comandos (mpremote):
```bash
pip install mpremote
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

## 🌐 Instrucciones de Uso de la Interfaz Web

1. **Obtener la dirección IP:**
   Al encender el ESP32, observa la salida en la consola serial de Thonny:
   ```text
   Intentando conectar a Wi-Fi 'MiHogar_2.4G'......
   =============================================
    Wi-Fi Conectado con éxito!
    Dirección IP asignada: http://192.168.1.85
   =============================================
   Servidor web iniciado y esperando peticiones en el puerto 80...
   ```

2. **Acceder desde un navegador:**
   Desde un teléfono móvil o computadora conectada a la misma red Wi-Fi, abre el navegador e ingresa la dirección:
   ```
   http://192.168.1.85
   ```

3. **Operación del Tablero:**
   * **Interruptor individual:** Desliza el switch de cualquier contacto para encender o apagar la corriente. El badge cambiará inmediatamente a **ENCENDIDO** (verde) o **APAGADO** (gris).
   * **Botones maestros:** Permiten conmutar todos los contactos al mismo tiempo ("Encender Todos" / "Apagar Todos").

4. **¿Qué hacer si no hay red Wi-Fi disponible? (Modo AP)**
   Si el ESP32 no encuentra la red configurada en 10 segundos:
   * Emitirá una red propia llamada **`ESP32-Multicontacto`**.
   * Conéctate a ella con la contraseña: **`multicontacto123`**.
   * Abre tu navegador e ingresa a: **`http://192.168.4.1`**.

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
