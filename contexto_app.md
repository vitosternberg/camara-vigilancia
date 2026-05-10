# Contexto de la Aplicación de Vigilancia y Reconocimiento Facial

Esta aplicación está compuesta por un conjunto de scripts en Python orientados a crear un sistema de vigilancia con reconocimiento facial, conectándose a una cámara IP Reolink. A continuación se describe el propósito y la funcionalidad de los componentes principales:

## 1. `main2.py` (Aplicación Principal - Interfaz Web)
Es la versión más completa y robusta de la aplicación, construida con **Streamlit**. Actúa como un "Sistema de Vigilancia Pro".
- **Interfaz y Control:** Permite iniciar y detener la cámara desde la barra lateral.
- **Base de Datos de Rostros:** Carga automáticamente las fotos ubicadas en el directorio `/Applications/XAMPP/xamppfiles/htdocs/camara/fotos/` para usarlas como rostros conocidos.
- **Reconocimiento Facial:** Utiliza la librería `face_recognition` para identificar si las personas en el video coinciden con las imágenes guardadas.
- **Sistema de Alertas y Enfriamiento:** Cuenta las veces que se detecta a una persona y usa una lógica de "enfriamiento" (configurable en minutos) para no spamear alertas consecutivas.
- **Estadísticas:** Muestra un dashboard inferior con el conteo de detecciones por persona.
- *Nota actual:* Actualmente está configurado para usar la cámara web local (`cv2.VideoCapture(0)`), pero tiene un comentario indicando que se debe cambiar a la URL de la cámara Reolink cuando se resuelva el hardware.

## 2. `main.py` (Prueba de Concepto - PoC)
Es un script más básico que ejecuta una ventana local usando `cv2.imshow`.
- **Conexión:** Se conecta directamente al stream RTSP de la cámara Reolink (`rtsp://admin:Rafa2422!@192.168.100.182:9000/h264Preview_01_main`).
- **Funcionalidad:** Captura el video, reduce la resolución para agilizar el procesamiento, detecta los rostros y dibuja un rectángulo verde con el texto "Persona Detectada". No identifica a la persona (no usa fotos de referencia).

## 3. `desbloqueo.py` (Script de Configuración de Red/Cámara)
Es una utilidad para habilitar los puertos necesarios en la cámara Reolink mediante su API HTTP.
- Se conecta a `http://192.168.100.182:9000/cgi-bin/api.cgi` usando las credenciales de administrador.
- Envía un payload JSON (`cmd: SetNetPort`) para habilitar activamente (`isRtsp: 1`, `isOnvif: 1`) los puertos RTSP (554) y ONVIF (9000). Esto es necesario para que `main.py` o `main2.py` puedan capturar el flujo de video.

## Dependencias Principales
- `streamlit`: Interfaz web.
- `cv2` (OpenCV): Procesamiento de imágenes y captura de video.
- `face_recognition`: Detección y comparación de rostros.
- `requests`: Peticiones HTTP a la API de la cámara.
- `numpy`, `os`, `time`, `datetime`.