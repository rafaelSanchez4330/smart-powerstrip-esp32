# Lista de Materiales (Bill of Materials - BOM)
## Proyecto: Multicontacto Inteligente con ESP32 y MicroPython

Este documento detalla los componentes, herramientas y especificaciones necesarias para la construcción del multicontacto inteligente con control web y aislamiento galvánico mediante relevadores.

---

### 1. Etapa de Control y Procesamiento (Baja Tensión - 3.3V / 5V DC)

| Componente | Especificaciones recomendadas | Cantidad | Función en el sistema |
| :--- | :--- | :---: | :--- |
| **Placa de desarrollo ESP32** | Modelo ESP32 DevKit V1 (30 o 38 pines) con chip ESP-WROOM-32. Conectividad Wi-Fi 802.11 b/g/n y Bluetooth LE. | 1 | Microcontrolador central. Alberga el firmware MicroPython, hospeda el servidor web y conmuta las salidas lógicas (GPIOs). |
| **Cable de datos USB a Micro-USB o Tipo-C** | Cable con líneas de datos habilitadas (no solo de carga), longitud 1 m. | 1 | Programación del firmware y depuración serial con la computadora. |
| **Cables de conexión (Jumpers)** | Cables dupont Hembra-Hembra y Macho-Hembra (20 cm, 24 AWG). | 1 paquete (~15 pzas) | Interconexión entre los pines GPIO/alimentación del ESP32 y las entradas del módulo de relés. |
| **Protoboard o Placa fenólica perforada (PCB)** | Mini protoboard o placa de pruebas de 4x6 cm (opcional para montaje definitivo). | 1 | Distribución de voltajes comunes (5V, 3.3V, GND) y soporte físico de conexiones. |

---

### 2. Etapa de Conmutación y Aislamiento

| Componente | Especificaciones recomendadas | Cantidad | Función en el sistema |
| :--- | :--- | :---: | :--- |
| **Módulo de Relevadores (Relay Module)** | Módulo de **4 canales** (o 2 canales según diseño) de 5V DC con optoacopladores integrados (aislamiento óptico). Capacidad de conmutación: 10A @ 125/250 VAC, 10A @ 30 VDC. Lógica activa en bajo (Active-LOW) con jumpers de selección JD-VCC / VCC. | 1 | Actúa como interruptor controlado electrónicamente para cortar o permitir el paso de la línea viva (Fase) hacia cada tomacorriente. |
| **LEDs indicadores de estado (Opcional)** | LEDs de 3mm o 5mm (verde/rojo) con resistencias de 330 $\Omega$ (si se desean indicadores visibles en el chasis exterior). | 4 | Señalización visual externa del estado encendido/apagado de cada toma de corriente. |

---

### 3. Etapa de Alimentación Interna (Conversión AC-DC)

> [!NOTE]
> Para que el multicontacto sea autónomo e inalámbrico sin depender de una computadora, requiere alimentarse de la misma toma de corriente de pared.

| Opción | Componente / Modelo | Cantidad | Descripción |
| :---: | :--- | :---: | :--- |
| **Opción A (Recomendada)** | **Cargador/Eliminador USB compacto (5V @ 2A)** | 1 | Un cargador comercial de celular desmontado o conectado en el interior. Provee aislamiento certificado y voltaje regulado de 5V tanto para la bobina de los relés como para el pin `VIN` / `5V` del ESP32. |
| **Opción B (Integrada)** | **Módulo convertidor Hi-Link HLK-PM01** | 1 | Entrada 100-240 VAC, Salida 5V DC @ 600mA (3W). Compacto para montaje en PCB o protoboard. |

---

### 4. Etapa de Potencia Eléctrica (Alta Tensión - 110V / 220V AC)

| Componente | Especificaciones recomendadas | Cantidad | Función en el sistema |
| :--- | :--- | :---: | :--- |
| **Tomacorrientes (Contactos eléctricos)** | Receptáculos dobles (duplex) o individuales para empotrar/chasis, 15A / 125VAC con conexión a tierra (NEMA 5-15R). | 2 a 4 módulos | Conectores hembra donde se enchufarán los aparatos eléctricos a controlar. |
| **Cable de alimentación principal con clavija** | Cable de uso rudo calibre **14 AWG o 16 AWG** (3 hilos: Fase, Neutro, Tierra) con clavija aterrizada macho de uso rudo (15A / 125V). Longitud 1.5 a 2 m. | 1 | Conexión principal del multicontacto a la red eléctrica doméstica. |
| **Cable unipolar de potencia para cableado interno** | Cable de cobre THW o THHN calibre **14 AWG** (preferiblemente en colores: Negro/Café para Fase, Blanco para Neutro, Verde para Tierra). | ~3 metros total | Distribución interna de la corriente de alta tensión hacia los relevadores y contactos. |
| **Portafusible y Fusible de protección** | Portafusible para chasis o aéreo con fusible de acción rápida de vidrio/cerámica de **10A / 250V**. | 1 | Protección contra sobrecorrientes y cortocircuitos en la línea principal de Fase. |
| **Clemas o Conectores de resorte rápido (tipo WAGO 221)** | Conectores de 3 y 5 vías para derivación de cables sin empalmes sueltos. | 3 a 5 pzas | Distribución segura de Neutro común y Tierra física entre todas las tomas. |

---

### 5. Gabinete y Envolvente (Estructura y Seguridad Mecánica)

| Componente | Especificaciones recomendadas | Cantidad | Función |
| :--- | :--- | :---: | :--- |
| **Caja o Gabinete de montaje** | Caja de conexiones plástica para sobreponer (caja registro de PVC ignífugo, dimensiones mínimas 15x15x7 cm) o gabinete diseñado e impreso en 3D (material PETG o ABS retardante de llama). | 1 | Contener y aislar físicamente los componentes de alta tensión de los circuitos lógicos de baja tensión y del contacto humano. |
| **Prensacables (Glandula pasamuros PG9 o PG11)** | De nylon plástico con empaque de goma. | 1 | Sujetar firmemente el cable de entrada para evitar que jalones accidentales desconecten cables en el interior. |
| **Tornillería y separadores de nylon (Standoffs)** | Separadores M3 de plástico de 10 mm con sus tornillos y tuercas. | 8 a 12 juegos | Fijar rígidamente la placa ESP32 y el módulo de relés a la base del gabinete, impidiendo cortocircuitos por contacto. |

---

### 6. Herramientas y Consumibles para Ensamble

* **Multímetro digital:** Esencial para medir continuidad, voltajes en vacío y comprobar la ausencia de cortocircuitos antes de energizar a 110V/220V.
* **Pinzas pelacables y de corte:** Para trabajar con calibres 14-24 AWG.
* **Desarmadores de precisión y de electricista:** Puntas planas y de cruz (Phillips).
* **Cautín de 30W-60W, soldadura de estaño 60/40 y pasta para soldar.**
* **Tubo termorretráctil (termoencogible):** De varios diámetros (3 mm a 8 mm) para aislar todas las terminales soldadas o expuestas.
* **Pistola de calor** o encendedor para contraer el tubo termoencogible.
* **Cinta aislante de vinilo de grado eléctrico (3M Temflex o similar).**
* **Terminales eléctricas de tipo ojo o pala (opcional):** Para atornillar con firmeza a los bornes de los relevadores y tomacorrientes.

---

### 7. Resumen de Consideraciones Críticas de Seguridad

1. **Separación física de zonas:** Mantener al menos 2 cm de separación o una barrera física aislante entre las pistas/cables de 110V/220V AC y los pines de 3.3V/5V del ESP32.
2. **Corte en la Fase (Línea Viva):** El relevador **siempre** debe cortar el cable de **Fase** ($L$), jamás el Neutro ($N$). Si se corta el Neutro, el aparato parecerá apagado pero mantendrá potencial eléctrico vivo, representando riesgo de electrocución.
3. **Calibre de cable adecuado:** Utilizar calibre 14 AWG para la corriente nominal de 10-15A de los contactos para evitar calentamiento por efecto Joule.
4. **Dimensionamiento de carga:** Los relevadores de 10A soportan típicamente hasta $10A \times 120V \approx 1200W$ resistivos por canal. No conectar electrodomésticos de alto consumo inductivo continuo (ej. calentadores de agua, motores industriales o aires acondicionados) sin relevadores de estado sólido o contactores industriales apropiados.

