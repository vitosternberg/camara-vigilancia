from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import cv2
import asyncio
import logging
import os
from datetime import datetime, timedelta
import face_recognition
import numpy as np
import pandas as pd
import requests

# --- 📝 CONFIGURACIÓN DE LOGS ---
# Configurar el sistema de logging para guardar eventos en un archivo
# Asegurarse de que el directorio del log exista si no está en la raíz
log_dir = os.path.join(os.path.dirname(__file__), '../../') # Apunta al directorio raíz del proyecto
log_file_path = os.path.join(log_dir, 'sistema_vigilancia.log')

logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logger.info("=== Iniciando Backend FastAPI de Vigilancia ===")

# --- 🔐 CONFIGURACIÓN DE SEGURIDAD E INTELIGENCIA ---
TELEGRAM_TOKEN = "8737879930:AAHBqVqTvEHS-sXsSQyFG-xfwboottjFjYw"
TELEGRAM_CHAT_ID = "5835369596"
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
ARCHIVO_HISTORICO = os.path.join(BASE_DIR, "historial_seguridad_poc.csv")

minutos_enfriamiento = 3
umbral_alerta = 3
alertas_activas = True
registro_tiempos = {} # Reemplazo de st.session_state en FastAPI

def inicializar_archivo():
    if not os.path.exists(ARCHIVO_HISTORICO):
        df = pd.DataFrame(columns=["Nombre", "Fecha", "Hora", "Datetime"])
        df.to_csv(ARCHIVO_HISTORICO, index=False)

def enviar_alerta_telegram(nombre, conteo):
    mensaje = (
        f"🚨 <b>ALERTA DE SEGURIDAD CRÍTICA</b> 🚨\n\n"
        f"<b>Sujeto detectado:</b> {nombre}\n"
        f"<b>Incidencia:</b> Detectado {conteo} veces en menos de {minutos_enfriamiento} minutos.\n"
        f"<b>Hora del reporte:</b> {datetime.now().strftime('%H:%M:%S')}\n"
        f"<i>⚠️ Acción: Se recomienda verificar cámaras o avisar a seguridad.</i>"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        logger.info(f"Alerta de Telegram enviada exitosamente para: {nombre} (conteo: {conteo})")
    except Exception as e:
        logger.error(f"Error al enviar Telegram: {e}")

def procesar_seguridad_poc(nombre):
    if nombre == "Desconocido":
        return

    ahora = datetime.now()
    timestamp_actual = ahora.timestamp()
    
    global registro_tiempos
    ultima_vez = registro_tiempos.get(nombre, 0)
    segundos_enfriamiento = minutos_enfriamiento * 60 

    if (timestamp_actual - ultima_vez) > segundos_enfriamiento:
        nuevo_reg = {
            "Nombre": nombre,
            "Fecha": ahora.strftime("%Y-%m-%d"),
            "Hora": ahora.strftime("%H:%M:%S"),
            "Datetime": ahora.strftime("%Y-%m-%d %H:%M:%S")
        }
        pd.DataFrame([nuevo_reg]).to_csv(ARCHIVO_HISTORICO, mode='a', header=False, index=False)
        
        registro_tiempos[nombre] = timestamp_actual
        logger.info(f"✅ Registro guardado en historial: {nombre}")

        df_h = pd.read_csv(ARCHIVO_HISTORICO)
        df_h['Datetime'] = pd.to_datetime(df_h['Datetime'])
        hace_ventana_riesgo = ahora - timedelta(minutes=minutos_enfriamiento)
        
        registros_recientes = df_h[(df_h['Nombre'] == nombre) & (df_h['Datetime'] > hace_ventana_riesgo)]
        conteo_total = len(registros_recientes)

        if conteo_total >= umbral_alerta:
            if alertas_activas:
                enviar_alerta_telegram(nombre, conteo_total)
            logger.warning(f"🚨 ESCALAMIENTO ACTIVO: {nombre} detectado {conteo_total} veces. Alerta enviada.")

def cargar_rostros():
    logger.info("Iniciando carga de base de datos de rostros...")
    ruta_fotos = os.path.join(BASE_DIR, "todos")
    conocidos_encodings = []
    conocidos_nombres = []
    
    if not os.path.exists(ruta_fotos):
        logger.error(f"Carpeta de fotos no encontrada en: {ruta_fotos}")
        return [], []

    archivos_procesados = 0
    for archivo in os.listdir(ruta_fotos):
        if archivo.lower().endswith((".jpg", ".png", ".jpeg")):
            archivos_procesados += 1
            try:
                img = face_recognition.load_image_file(os.path.join(ruta_fotos, archivo))
                encs = face_recognition.face_encodings(img)
                if encs:
                    conocidos_encodings.append(encs[0])
                    conocidos_nombres.append(os.path.splitext(archivo)[0])
                else:
                    logger.warning(f"No se encontró un rostro en la imagen: {archivo}")
            except Exception as e:
                logger.error(f"Error cargando {archivo}: {e}")
                
    logger.info(f"Carga finalizada. {len(conocidos_encodings)} rostros cargados de {archivos_procesados} válidos.")
    return conocidos_encodings, conocidos_nombres

# Inicializar base de datos y memoria
inicializar_archivo()
encodings_db, nombres_db = cargar_rostros()

def procesar_frame(frame):
    frame = cv2.flip(frame, 1) # Efecto espejo
    if not encodings_db:
        return frame
        
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
    
    face_locs = face_recognition.face_locations(rgb_small_frame)
    face_encs = face_recognition.face_encodings(rgb_small_frame, face_locs)

    for (top, right, bottom, left), face_enc in zip(face_locs, face_encs):
        face_distances = face_recognition.face_distance(encodings_db, face_enc)
        nombre = "Desconocido"
        color = (0, 0, 255) # Rojo

        if len(face_distances) > 0:
            best_match_index = np.argmin(face_distances)
            if face_distances[best_match_index] <= 0.5:
                nombre = nombres_db[best_match_index]
                color = (0, 255, 0) # Verde
        
        procesar_seguridad_poc(nombre)
        
        top *= 4; right *= 4; bottom *= 4; left *= 4
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, nombre, (left, top-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
        
    return frame

app = FastAPI()

# Montar la carpeta 'frontend' para servir archivos estáticos (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), '../frontend')), name="static")

# --- CONTROL DE CÁMARA ---
camera = None
# Usar un lock para asegurar que solo un generador acceda a la cámara a la vez
camera_lock = asyncio.Lock() 

async def get_frame_generator():
    global camera
    if camera is None or not camera.isOpened():
        camera = cv2.VideoCapture(0)  # Usar la cámara de la Mac (0)
        if not camera.isOpened():
            logger.error("No se pudo abrir la cámara.")
            return

    while True:
        try:
            async with camera_lock: # Asegura acceso exclusivo a la cámara
                # Leer la cámara en un hilo separado para no bloquear el Event Loop
                ret, frame = await asyncio.to_thread(camera.read)
                
            if not ret:
                logger.warning("No se pudo leer el frame de la cámara. Reintentando...")
                await asyncio.sleep(0.1) # Esperar un poco antes de reintentar
                continue
                
            # Aplicar reconocimiento facial, dibujar e inteligencia en un hilo separado
            frame = await asyncio.to_thread(procesar_frame, frame)

            # Codificar la imagen (operación pesada de CPU) en un hilo separado
            ret, buffer = await asyncio.to_thread(cv2.imencode, '.jpg', frame)
            if not ret:
                logger.error("No se pudo codificar el frame como JPEG.")
                continue
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n'
                   b'Content-Length: ' + str(len(buffer)).encode() + b'\r\n'
                   b'\r\n' + buffer.tobytes() + b'\r\n')
            
            # Pequeña pausa para evitar saturar el CPU y permitir cambio de contexto
            await asyncio.sleep(0.01)
            
        except asyncio.CancelledError:
            logger.info("El cliente cerró la conexión del stream.")
            break
        except Exception as e:
            logger.error(f"Error en el generador de frames: {e}")
            break
        finally:
            # Importante: No liberar la cámara aquí si se espera que persista
            # Liberar la cámara solo si la app se detiene o el stream finaliza
            pass

@app.get("/")
async def read_root():
    # Servir el archivo index.html desde la carpeta static
    frontend_path = os.path.join(os.path.dirname(__file__), '../frontend/index.html')
    if os.path.exists(frontend_path):
        with open(frontend_path, "r") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content="<h1>Frontend no encontrado</h1><p>Asegúrate de que 'index.html' esté en la carpeta 'app_web/frontend'.</p>", status_code=404)

@app.get("/video_feed")
async def video_feed():
    logger.info("Solicitud de /video_feed recibida.")
    return StreamingResponse(get_frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/stats")
async def get_stats():
    if not os.path.exists(ARCHIVO_HISTORICO):
        return {"total": 0, "recent": []}
    
    try:
        df = pd.read_csv(ARCHIVO_HISTORICO)
        if df.empty:
            return {"total": 0, "recent": []}
            
        # Filtrar a los desconocidos y obtener total general
        df_conocidos = df[df['Nombre'] != 'Desconocido']
        total_eventos = len(df_conocidos)
        
        # Agrupar por nombre para generar las tarjetas resumen
        resumen = df_conocidos.groupby('Nombre').agg(
            conteo=('Nombre', 'count'),
            ultima_vez=('Datetime', 'max')
        ).reset_index()
        
        # Ordenar por fecha más reciente y sacar el top 5
        resumen = resumen.sort_values(by='ultima_vez', ascending=False).head(5)
        
        recent = []
        for _, row in resumen.iterrows():
            recent.append({"nombre": row['Nombre'], "conteo": row['conteo'], "ultima_vez": row['ultima_vez']})
            
        return {"total": total_eventos, "recent": recent}
    except Exception as e:
        logger.error(f"Error al leer estadísticas para dashboard: {e}")
        return {"total": 0, "recent": []}

@app.on_event("shutdown")
async def shutdown_event():
    global camera
    if camera is not None:
        camera.release()
        logger.info("Cámara liberada al apagar la aplicación.")

if __name__ == "__main__":
    # Para ejecutar: uvicorn app_web.backend.main:app --reload
    # El --reload es útil para desarrollo, pero para producción, se usa sin --reload
    logger.info("Uvicorn está iniciando el servidor FastAPI.")
    
    # Usamos el formato de string "main:app" y activamos reload=True.
    # También le indicamos que vigile tanto la carpeta backend como la de frontend.
    frontend_dir = os.path.join(os.path.dirname(__file__), '../frontend')
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True, reload_dirs=[os.path.dirname(__file__), frontend_dir])
