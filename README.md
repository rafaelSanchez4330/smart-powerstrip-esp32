# Multicontacto Inteligente con ESP32 / ESP32-S3 y MicroPython
> **Proyecto Académico de Sistemas Embebidos e Internet de las Cosas (IoT)**

Este repositorio contiene el diseño, código fuente y documentación técnica para la construcción de un **multicontacto eléctrico inteligente (`SmartPS`)** controlado mediante un microcontrolador **ESP32-S3 / ESP32** programado en **MicroPython**. El sistema integra un servidor web embebido, un gestor de configuración Wi-Fi persistente y un servidor DNS local que permite configurar la red y conmutar individualmente cada contacto eléctrico desde cualquier navegador web (celular, tablet o PC).

---

## 📋 Tabla de Contenidos

1. [Características Principales](#-características-principales)
2. [Arquitectura del Sistema](#-arquitectura-del-sistema)
3. [Guía Paso a Paso: Cómo Flashear y Cargar el Código desde PowerShell](#-guía-paso-a-paso-cómo-flashear-y-cargar-el-código-desde-powershell)
4. [Conexión Física de Componentes (Pinout y Potencia)](#-conexión-física-de-componentes-pinout-y-potencia)
5. [Cómo Encender el Sistema y Conmutar los Contactos](#-cómo-encender-el-sistema-y-conmutar-los-contactos)
6. [Guía de Configuración: Primera Vez vs. Uso Diario](#-guía-de-configuración-primera-vez-vs-uso-diario)
7. [Medidas de Seguridad Eléctrica](#-medidas-de-seguridad-eléctrica)
8. [Lista de Materiales (BOM)](#-lista-de-materiales-bom)

---

## 🚀 Características Principales

* **Servidor Web Embebido Autónomo:** Opera directamente dentro de la red local sin depender de servicios en la nube externos.
* **Control Multicanal:** Conmutación independiente o grupal de 4 relevadores (GPIO `15`, `16`, `17` y `18`).
* **Portal de Configuración Wi-Fi ("Wi-Fi Manager"):** Escanea redes Wi-Fi 2.4 GHz cercanas y permite guardar las credenciales desde el navegador en un archivo permanente (`wifi_config.json`) en la memoria Flash.
* **Dominio Interno (`http://smartps.local`):** Incluye un micro-servidor DNS en el puerto UDP `53` para el modo Punto de Acceso y registro de hostname DHCP/mDNS para la red local.
* **Modo Punto de Acceso (AP) Protegido:** Cuando no hay red configurada o no está disponible, levanta su propia red Wi-Fi **`SmartPS`** (contraseña **`SmartPS123`**) y solicita la clave de seguridad **`SmartPS`** en la web para autorizar cambios de red.
* **Inicialización Segura de Pines:** Garantiza que todos los relevadores inicien apagados al energizar la placa, evitando chispazos o encendidos involuntarios.

---

## 🏛 Arquitectura del Sistema

```
[ Celular / PC (Navegador Web: http://smartps.local) ]
         │
         ▼
[ Red Wi-Fi Local (Router)  ó  Punto de Acceso Propio "SmartPS" ]
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│                     ESP32-S3 / ESP32                         │
│  - Firmware: MicroPython v1.24+                              │
│  - Módulos: main.py + wifi_manager.py + wifi_config.json     │
│  - Servidor Web HTTP (Puerto 80) + Servidor DNS (Puerto 53)  │
│  - Salidas GPIO: Pines 15, 16, 17 y 18                       │
└──────────────────────────────────────────────────────────────┘
         │ (Señales lógicas 3.3V - Active LOW)
         ▼
┌──────────────────────────────────────────────────────────────┐
│        Módulo de 4 Relevadores de 5V (Optoacoplado)          │
│  - Aislamiento galvánico entre control (DC) y potencia (AC)  │
└──────────────────────────────────────────────────────────────┘
         │ (Conmutación mecánica de Fase - 110V/127V AC)
         ▼
[ Contactos Eléctricos 1, 2, 3 y 4 ] ──► [ Electrodomésticos / Cargas ]
```

---

## ⚡ Guía Paso a Paso: Cómo Flashear y Cargar el Código desde PowerShell

En MicroPython no es necesario compilar el código Python. El proceso consiste en grabar el intérprete de MicroPython (`.bin`) en la memoria Flash una sola vez y luego copiar los archivos [`src/wifi_manager.py`](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/src/wifi_manager.py) y [`src/main.py`](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/src/main.py) a la raíz del microcontrolador.

### Paso 1: Instalar las herramientas en PowerShell
Abre **PowerShell** en la carpeta raíz del proyecto y ejecuta:

```powershell
python -m pip install esptool mpremote
```

### Paso 2: Identificar el puerto `COM` de la placa ESP32
Conecta la placa a la computadora con un **cable USB con soporte de datos** y ejecuta en PowerShell:

```powershell
Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match "COM\d+" } | Select-Object Name
```
* Busca el puerto que diga **`Dispositivo serie USB (COMx)`**, **`Silicon Labs CP210x (COMx)`** o **`USB-SERIAL CH340 (COMx)`** (por ejemplo, `COM8`).
* *(Ignora los puertos que digan "Serie estándar sobre el vínculo Bluetooth").*

### Paso 3: Descargar e instalar el firmware de MicroPython
Reemplaza **`COM8`** por el puerto COM que apareció en el paso anterior:

#### A) Si tu placa es **ESP32-S3** (como la usada en este proyecto):
```powershell
# 1. Descargar firmware oficial para ESP32-S3
Invoke-WebRequest -Uri "https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20241129-v1.24.1.bin" -OutFile "firmware_s3.bin"

# 2. Borrar la memoria Flash
python -m esptool --chip esp32s3 --port COM8 erase-flash

# 3. Flashear el firmware en la dirección 0x0
python -m esptool --chip esp32s3 --port COM8 --baud 460800 write-flash 0x0 firmware_s3.bin
```

#### B) Si tu placa es una **ESP32 Clásica (ESP-WROOM-32)**:
```powershell
# 1. Descargar firmware oficial para ESP32 genérico
Invoke-WebRequest -Uri "https://micropython.org/resources/firmware/ESP32_GENERIC-20241129-v1.24.1.bin" -OutFile "firmware_esp32.bin"

# 2. Borrar la memoria Flash
python -m esptool --chip esp32 --port COM8 erase-flash

# 3. Flashear el firmware en la dirección 0x1000
python -m esptool --chip esp32 --port COM8 --baud 460800 write-flash 0x1000 firmware_esp32.bin
```

> [!TIP]
> Si `esptool` se queda esperando en `Connecting........`, mantén presionado el botón físico **BOOT** de la placa durante 2 segundos. Al terminar de flashear, presiona una vez el botón físico **RST / EN**.

### Paso 4: Subir los módulos del proyecto a la ESP32
Copia ambos archivos dentro de la raíz (`:`) de la memoria de la ESP32 y reiníciala:

```powershell
python -m mpremote connect COM8 cp src/wifi_manager.py :wifi_manager.py
python -m mpremote connect COM8 cp src/main.py :main.py
python -m mpremote connect COM8 reset
```

### Paso 5: Verificar la ejecución en la consola (Opcional)
Para abrir el monitor serial en vivo desde PowerShell:

```powershell
python -m mpremote connect COM8 repl
```
* Una vez dentro, presiona **`Ctrl + C`** y luego **`Ctrl + D`** para reiniciar suavemente y ver en pantalla el estado de la conexión Wi-Fi y la dirección IP.
* Para salir del monitor serial sin detener la placa, presiona **`Ctrl + ]`** o **`Ctrl + X`**.

---

## 🔌 Conexión Física de Componentes (Pinout y Potencia)

### 1. Conexiones de Baja Tensión (ESP32 ──► Módulo de 4 Relevadores)

Conecta los pines de la placa ESP32-S3 / ESP32 a la tira de pines de entrada del módulo de relevadores utilizando cables Dupont:

| Puerto / Pin en ESP32 | Pin en Módulo de Relevadores | Componente Controlado | Función |
| :---: | :---: | :--- | :--- |
| **5V / VIN** | **VCC** | Alimentación de bobinas (5V DC) | Energiza los electroimanes del módulo de relés. |
| **GND** | **GND** | Tierra común (0V) | Referencia eléctrica común entre el ESP32 y el módulo. |
| **GPIO 15** | **IN1** | **Contacto 1** | Señal digital de control del Relevador 1. |
| **GPIO 16** | **IN2** | **Contacto 2** | Señal digital de control del Relevador 2. |
| **GPIO 17** | **IN3** | **Contacto 3** | Señal digital de control del Relevador 3. |
| **GPIO 18** | **IN4** | **Contacto 4** | Señal digital de control del Relevador 4. |

> [!WARNING]
> **Notas sobre Pines en ESP32-S3 y ESP32:**
> - En **ESP32-S3**, **no uses los pines GPIO 19 y GPIO 20** para relevadores, ya que corresponden a las líneas de datos (`D-` y `D+`) del puerto USB nativo. Los pines **15, 16, 17 y 18** son consecutivos y completamente seguros.
> - Evita los pines de configuración de arranque (*strapping pins*: `0, 3, 45, 46` en ESP32-S3; `0, 2, 12` en ESP32 clásico) y los pines de memoria Flash interna.

---

### 2. Conexiones de Alta Tensión (110V / 127V AC ──► Bornes de Relevadores y Contactos)

Cada relevador tiene 3 bornes con tornillo del lado de potencia: **`NO`** (Normalmente Abierto), **`COM`** (Común) y **`NC`** (Normalmente Cerrado).

> [!CAUTION]
> **REGLA DE ORO DE SEGURIDAD ELÉCTRICA:**
> Los relevadores deben interrumpir **únicamente el cable de Fase (Línea Viva)**, nunca el Neutro ni la Tierra Física. Realiza todo el cableado con la clavija principal **desconectada de la pared**.

| Cable de Entrada (Clavija Principal) | Hacia dónde se conecta | Destino final en los 4 Tomacorrientes (Contactos) |
| :--- | :--- | :--- |
| **Fase / Línea Viva** (Negro o Café) | Pasa por el **Fusible de 10A** y se reparte en puente a los 4 terminales centrales **`COM 1`**, **`COM 2`**, **`COM 3`** y **`COM 4`** de los relevadores. | Del borne **`NO 1`** sale hacia la **Ranura Corta** del Contacto 1.<br>Del borne **`NO 2`** sale hacia la **Ranura Corta** del Contacto 2.<br>Del borne **`NO 3`** sale hacia la **Ranura Corta** del Contacto 3.<br>Del borne **`NO 4`** sale hacia la **Ranura Corta** del Contacto 4.<br>*(Los bornes `NC` quedan libres sin cable).* |
| **Neutro** (Blanco o Azul) | Directo a una clema de unión común (WAGO). | Se conecta en paralelo a la **Ranura Ancha** de los 4 contactos. |
| **Tierra Física** (Verde o Desnudo) | Directo a una clema de unión común (WAGO). | Se conecta en paralelo al **Borne Redondo (U)** de los 4 contactos. |

```
Fase (Negro) ──[ Fusible 10A ]──┬──► [ COM 1 ] ──( NO 1 )──► Contacto 1 (Ranura Corta)
                                ├──► [ COM 2 ] ──( NO 2 )──► Contacto 2 (Ranura Corta)
                                ├──► [ COM 3 ] ──( NO 3 )──► Contacto 3 (Ranura Corta)
                                └──► [ COM 4 ] ──( NO 4 )──► Contacto 4 (Ranura Corta)

Neutro (Blanco) ─────────( Clema WAGO común )──────────────► Contactos 1, 2, 3 y 4 (Ranura Ancha)
Tierra (Verde)  ─────────( Clema WAGO común )──────────────► Contactos 1, 2, 3 y 4 (Borne U)
```

---

## 🔋 Cómo Encender el Sistema y Conmutar los Contactos

### 1. ¿Cómo se enciende la placa ESP32 (Arranque Autónomo)?
Una vez cargados `wifi_manager.py` y `main.py` en la placa, **no necesitas conectar una computadora**:
* Basta con alimentar la ESP32 mediante un **cargador USB de 5V (mínimo 1A - 1.5A)** conectado a su puerto USB, o mediante una fuente de 5V DC conectada a los pines `5V/VIN` y `GND`.
* En cuanto recibe energía, el firmware de MicroPython arranca automáticamente en ~2 segundos, ejecuta `main.py`, asegura que los 4 relevadores inicien **APAGADOS** y levanta el servidor web.

### 2. ¿Cómo se prenden y apagan los contactos eléctricos?
Los módulos de relevadores con optoacoplador funcionan con **lógica inversa (`RELAY_ACTIVE_LOW = True`)**, la cual el programa maneja automáticamente:
* **Para encender un contacto individual:** En la página web, toca el interruptor deslizable (*switch*) de la tarjeta correspondiente. El ESP32 pondrá el pin GPIO en `0V` (LOW), se encenderá el LED indicador de ese canal en el módulo de relevadores, se escuchará un *"clic"* mecánico cerrando el paso entre `COM` y `NO`, y la etiqueta en la web cambiará a **`ENCENDIDO`** (verde).
* **Para apagar un contacto individual:** Vuelve a tocar su interruptor deslizable. El ESP32 pondrá el pin GPIO en `3.3V` (HIGH), el relevador abrirá el circuito cortando la corriente y la etiqueta cambiará a **`APAGADO`** (gris).
* **Para encender o apagar todos a la vez:** Pulsa los botones inferiores **"Encender Todos"** o **"Apagar Todos"** en la interfaz web.

---

## 🌐 Guía de Configuración: Primera Vez vs. Uso Diario

### Escenario A: Configuración por Primera Vez (o cuando no hay Wi-Fi conocido)

Cuando enciendes el multicontacto por primera vez (o lo llevas a un lugar nuevo donde no está la red Wi-Fi guardada):

1. **Espera 5 segundos tras enchufarlo:** El ESP32 detectará que no hay red configurada y creará su propio Punto de Acceso Wi-Fi.
2. **Conéctate a la red Wi-Fi del ESP32 desde tu celular o laptop:**
   * **Nombre de red (SSID):** `SmartPS`
   * **Contraseña del Wi-Fi:** `SmartPS123`
3. **Abre la interfaz web en tu navegador (`http://smartps.local` o `http://192.168.4.1`):**
   Al estar en Modo Punto de Acceso (sin red Wi-Fi conectada), aparecerá una **Pantalla de Inicio** con dos opciones:
   * **📶 Conectar a una Red Wi-Fi:** Abre el buscador de redes para vincular el multicontacto a tu módem.
   * **🔌 Acceder a los Interruptores:** Te lleva directamente al tablero de control para prender/apagar los 4 contactos y personalizar sus nombres (tocando el botón **`✏️`** al lado de cada contacto; los nombres se guardan en `relays_names.json`).
4. **Vincula el multicontacto al Wi-Fi de tu casa/escuela:**
   * En la página web, pulsa el botón **"⚙️ Configurar Red Wi-Fi"**.
   * El panel buscará automáticamente las redes Wi-Fi **2.4 GHz** cercanas. Selecciona tu red de la lista desplegable.
   * Escribe la **contraseña de tu red Wi-Fi**.
   * En el campo **"Clave de Seguridad del Dispositivo"**, escribe: **`SmartPS`**
   * Pulsa **"Guardar y Conectar"**.
5. **Confirmación de nueva dirección IP:**
   * El ESP32 se conectará a tu módem, guardará las credenciales en `wifi_config.json` y mostrará un recuadro verde en pantalla indicando la **nueva dirección IP asignada** por tu router (ejemplo: `http://192.168.1.85`) junto con el enlace **`http://smartps.local`**.
   * Pasados 15 segundos, el ESP32 apagará el Punto de Acceso `SmartPS` para quedar operando únicamente dentro de tu red local.

---

### Escenario B: Uso Diario (Una vez que ya fue configurado)

Una vez que guardaste tu red Wi-Fi en el Escenario A:

1. **Encendido automático:** Cada vez que desconectes el multicontacto y lo vuelvas a enchufar a la corriente, el ESP32 leerá automáticamente el archivo `wifi_config.json` y se conectará en pocos segundos al Wi-Fi de tu casa sin pedirte nada.
2. **Acceso desde cualquier dispositivo de tu casa:**
   Asegúrate de que tu celular o PC esté conectado al Wi-Fi de tu casa y entra desde el navegador a:
   * **`http://smartps.local`** *(en PC, Mac, iPhone o dispositivos compatibles con mDNS)*, o
   * **`http://<IP-ASIGNADA>`** *(por ejemplo, `http://192.168.1.85`)*.
3. **¿Cómo cambiar de red Wi-Fi o reiniciar la configuración después?**
   Tienes dos formas:
   * **Desde la página web:** Abre **"⚙️ Configurar Red Wi-Fi"**, ingresa la clave **`SmartPS`** y elige otra red o pulsa el botón rojo **"Olvidar Red"** (esto borra `wifi_config.json` y vuelve a encender la red `SmartPS`).
   * **Automáticamente si apagas tu módem o te mudas:** Si al encender el multicontacto no encuentra la red guardada después de 10 segundos, **activa automáticamente la red de rescate `SmartPS`** (`SmartPS123`) para que nunca pierdas el acceso.

---

## ⚠️ Medidas de Seguridad Eléctrica

El voltaje de la red eléctrica doméstica (110V - 240V AC) es peligroso si se manipula sin precaución:

1. **Desconexión Total:** Realiza todo el ensamble, apriete de tornillos y empalmes con la clavija principal **desconectada del tomacorriente**.
2. **Aislamiento de Terminales:** Ningún alambre de cobre debe quedar expuesto fuera de las clemas WAGO o bornes de los relevadores.
3. **Protección con Fusible:** Instala siempre un fusible de 10A en la entrada de la Fase principal para proteger el módulo de relevadores ante sobrecargas.
4. **Gabinete Cerrado:** Aloja el circuito dentro de una caja plástica aislante antes de enchufarlo a la red eléctrica.
5. **Verificación con Multímetro:** Antes de conectar por primera vez a 110V/127V AC, verifica en modo continuidad que **no exista cortocircuito** entre Fase y Neutro ni entre Fase y Tierra.

---

## 📦 Lista de Materiales (BOM)

Para consultar la lista completa y detallada de componentes electrónicos, de potencia, consumibles y herramientas requeridas, visita el documento:
👉 **[docs/lista_de_materiales.md](file:///c:/Users/rafas/dev/smart-powerstrip-esp32/docs/lista_de_materiales.md)**
