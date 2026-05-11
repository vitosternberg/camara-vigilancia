from fastapi import FastAPI, Response, UploadFile, File, Form, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
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
import json
from dotenv import load_dotenv
import secrets

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

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
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
ARCHIVO_HISTORICO = os.path.join(BASE_DIR, "historial_seguridad_poc.csv")
METADATA_FILE = os.path.join(BASE_DIR, "app_web", "fotos", "metadata.json")

def cargar_metadata():
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def guardar_metadata(data):
    os.makedirs(os.path.dirname(METADATA_FILE), exist_ok=True)
    with open(METADATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

minutos_enfriamiento = 3
umbral_alerta = 3
alertas_activas = True
registro_tiempos = {} # Reemplazo de st.session_state en FastAPI

def inicializar_archivo():
    if not os.path.exists(ARCHIVO_HISTORICO):
        df = pd.DataFrame(columns=["Nombre", "Fecha", "Hora", "Datetime"])
        df.to_csv(ARCHIVO_HISTORICO, index=False)

def enviar_alerta_telegram(nombre, conteo, meta={}):
    accion = meta.get("accion", "Enviar notificación")
    peligrosidad = meta.get("peligrosidad", "Baja")
    accion_texto = "⚠️ Se recomienda verificar cámaras."
    if accion == "Llamar a seguridad":
        accion_texto = "🚓 LLAMAR A SEGURIDAD INMEDIATAMENTE."

    mensaje = (
        f"🚨 <b>ALERTA DE SEGURIDAD CRÍTICA</b> 🚨\n\n"
        f"<b>Sujeto detectado:</b> {nombre}\n"
        f"<b>Peligrosidad:</b> {peligrosidad}\n"
        f"<b>Incidencia:</b> Detectado {conteo} veces en menos de {minutos_enfriamiento} minutos.\n"
        f"<b>Hora del reporte:</b> {datetime.now().strftime('%H:%M:%S')}\n"
        f"<i>{accion_texto}</i>"
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
        
        # Ampliamos la ventana de riesgo para hacer matemáticamente posible alcanzar el umbral
        hace_ventana_riesgo = ahora - timedelta(minutes=(minutos_enfriamiento * umbral_alerta))
        registros_recientes = df_h[(df_h['Nombre'] == nombre) & (df_h['Datetime'] > hace_ventana_riesgo)]
        conteo_total = len(registros_recientes)

        if conteo_total >= umbral_alerta:
            meta = cargar_metadata().get(nombre, {})
            accion = meta.get("accion", "Enviar notificación")
            
            if accion != "No hacer nada" and alertas_activas:
                enviar_alerta_telegram(nombre, conteo_total, meta)
                logger.warning(f"🚨 ESCALAMIENTO ACTIVO: {nombre} detectado {conteo_total} veces. Alerta enviada.")
            else:
                logger.warning(f"⚠️ {nombre} detectado {conteo_total} veces, pero la acción es 'No hacer nada' o alertas apagadas.")

def cargar_rostros():
    logger.info("Iniciando carga de base de datos de rostros...")
    ruta_fotos = os.path.abspath(os.path.join(os.path.dirname(__file__), '../fotos'))
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

# --- 🛂 SISTEMA DE AUTENTICACIÓN Y ROLES ---
USERS = {
    "admin": {"password": "adminpassword", "role": "admin"},
    "guardia": {"password": "guardiapassword", "role": "guardia"},
    "visor": {"password": "visorpassword", "role": "visor"}
}
SESSIONS = {}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    # Si el formato del login o cualquier petición es incorrecto (Ej. falta usuario o contraseña)
    logger.error(f"Error de validación en la ruta {request.url.path}: {exc}")
    return JSONResponse(status_code=422, content={"detail": f"Error de formato en los datos: {exc}"})

@app.post("/api/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    logger.info(f"Intento de inicio de sesión para el usuario: '{form_data.username}'")
    user = USERS.get(form_data.username)
    if not user or user["password"] != form_data.password:
        logger.warning(f"⚠️ Intento fallido para: '{form_data.username}'. Credenciales incorrectas.")
        raise HTTPException(status_code=400, detail="Credenciales incorrectas")
        
    token = secrets.token_hex(16)
    SESSIONS[token] = {"username": form_data.username, "role": user["role"]}
    logger.info(f"✅ Inicio de sesión exitoso. Usuario: '{form_data.username}' | Rol: '{user['role']}'")
    return {"access_token": token, "token_type": "bearer", "role": user["role"]}

def get_current_user(token: str = Depends(oauth2_scheme)):
    user = SESSIONS.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    return user

def require_role(allowed_roles: list):
    def role_checker(user: dict = Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="No tienes permisos para esta acción")
        return user
    return role_checker

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

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(content=b"", media_type="image/x-icon")

@app.get("/video_feed")
async def video_feed(token: str = None):
    if not token or token not in SESSIONS:
        raise HTTPException(status_code=401, detail="No autorizado para ver video")
    logger.info("Solicitud de /video_feed recibida.")
    return StreamingResponse(get_frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

class ConfigSettings(BaseModel):
    minutos_enfriamiento: int
    umbral_alerta: int
    alertas_activas: bool

class EditPersonModel(BaseModel):
    nombre: str
    nuevo_nombre: str
    edad: int
    peligrosidad: str
    accion: str

@app.get("/api/settings")
async def get_settings(user=Depends(require_role(["admin", "guardia", "visor"]))):
    return {
        "minutos_enfriamiento": minutos_enfriamiento,
        "umbral_alerta": umbral_alerta,
        "alertas_activas": alertas_activas
    }

@app.post("/api/settings")
async def update_settings(settings: ConfigSettings, user=Depends(require_role(["admin"]))):
    global minutos_enfriamiento, umbral_alerta, alertas_activas
    minutos_enfriamiento = settings.minutos_enfriamiento
    umbral_alerta = settings.umbral_alerta
    alertas_activas = settings.alertas_activas
    logger.info(f"Configuración actualizada: {settings}")
    return {"status": "success", "message": "Configuración actualizada correctamente"}

@app.get("/api/stats")
async def get_stats(user=Depends(require_role(["admin", "guardia", "visor"]))):
    if not os.path.exists(ARCHIVO_HISTORICO):
        return {"total": 0, "recent": []}
    
    metadata = cargar_metadata()
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
        
        # Resumen completo ordenado por cantidad de veces vistas (para el Modal)
        resumen_all = resumen.sort_values(by='conteo', ascending=False)
        
        # Resumen reciente top 5 (para la barra rápida lateral)
        resumen_recent = resumen.sort_values(by='ultima_vez', ascending=False).head(5)
        
        recent = []
        for _, row in resumen_recent.iterrows():
            recent.append({"nombre": row['Nombre'], "conteo": row['conteo'], "ultima_vez": row['ultima_vez']})
            
        all_data = []
        for _, row in resumen_all.iterrows():
            nombre = row['Nombre']
            meta = metadata.get(nombre, {})
            all_data.append({
                "nombre": nombre, 
                "conteo": row['conteo'], 
                "ultima_vez": row['ultima_vez'],
                "edad": meta.get("edad", "N/A"),
                "peligrosidad": meta.get("peligrosidad", "Baja"),
                "accion": meta.get("accion", "No hacer nada")
            })
            
        return {"total": total_eventos, "recent": recent, "all": all_data}
    except Exception as e:
        logger.error(f"Error al leer estadísticas para dashboard: {e}")
        return {"total": 0, "recent": [], "all": []}

@app.delete("/api/clear_history")
async def clear_history(user=Depends(require_role(["admin", "guardia"]))):
    if os.path.exists(ARCHIVO_HISTORICO):
        df = pd.DataFrame(columns=["Nombre", "Fecha", "Hora", "Datetime"])
        df.to_csv(ARCHIVO_HISTORICO, index=False)
        
    global registro_tiempos
    registro_tiempos.clear()
    
    logger.info(f"🗑️ Historial de seguridad limpiado por el usuario: {user['username']}")
    return {"status": "success", "message": "El historial y los contadores se han borrado."}

@app.get("/foto/{nombre}")
async def get_foto(nombre: str, token: str = None):
    if not token or token not in SESSIONS:
        raise HTTPException(status_code=401, detail="No autorizado")
    ruta_fotos = os.path.abspath(os.path.join(os.path.dirname(__file__), '../fotos'))
    for ext in ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']:
        file_path = os.path.join(ruta_fotos, f"{nombre}{ext}")
        if os.path.exists(file_path):
            return FileResponse(file_path)
    return Response(status_code=404)

@app.get("/api/people")
async def get_people(user=Depends(require_role(["admin", "guardia"]))):
    ruta_fotos = os.path.abspath(os.path.join(os.path.dirname(__file__), '../fotos'))
    metadata = cargar_metadata()
    personas = []
    if os.path.exists(ruta_fotos):
        for archivo in os.listdir(ruta_fotos):
            if archivo.lower().endswith(('.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG')):
                nombre = os.path.splitext(archivo)[0]
                meta = metadata.get(nombre, {})
                personas.append({
                    "nombre": nombre,
                    "edad": meta.get("edad", "N/A"),
                    "peligrosidad": meta.get("peligrosidad", "Baja"),
                    "accion": meta.get("accion", "No hacer nada")
                })
    return {"status": "success", "personas": personas}

@app.post("/api/edit_person")
async def edit_person(data: EditPersonModel, user=Depends(require_role(["admin", "guardia"]))):
    metadata = cargar_metadata()
    nombre_actual = data.nombre
    nombre_nuevo = data.nuevo_nombre.strip()

    if nombre_actual not in metadata:
        metadata[nombre_actual] = {}
        
    metadata[nombre_actual]["edad"] = data.edad
    metadata[nombre_actual]["peligrosidad"] = data.peligrosidad
    metadata[nombre_actual]["accion"] = data.accion
    
    # Si el usuario modificó el nombre
    if nombre_nuevo and nombre_nuevo != nombre_actual:
        ruta_fotos = os.path.abspath(os.path.join(os.path.dirname(__file__), '../fotos'))
        
        # 1. Buscar la foto y renombrarla
        for ext in ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']:
            old_file = os.path.join(ruta_fotos, f"{nombre_actual}{ext}")
            if os.path.exists(old_file):
                new_file = os.path.join(ruta_fotos, f"{nombre_nuevo}{ext}")
                os.rename(old_file, new_file)
                break
        
        # 2. Actualizar el diccionario de metadata
        metadata[nombre_nuevo] = metadata.pop(nombre_actual)
        
        # 3. Actualizar los nombres en el historial para no perder las estadísticas
        try:
            if os.path.exists(ARCHIVO_HISTORICO):
                df = pd.read_csv(ARCHIVO_HISTORICO)
                if not df.empty and 'Nombre' in df.columns:
                    df.loc[df['Nombre'] == nombre_actual, 'Nombre'] = nombre_nuevo
                    df.to_csv(ARCHIVO_HISTORICO, index=False)
        except Exception as e:
            logger.error(f"Error al actualizar historial CSV con el nuevo nombre: {e}")

        # 4. Reentrenar la IA con el nuevo nombre
        global encodings_db, nombres_db
        encodings_db, nombres_db = cargar_rostros()

    guardar_metadata(metadata)
    logger.info(f"Metadatos actualizados para: {nombre_nuevo or nombre_actual}")
    return {"status": "success", "message": f"Datos de {nombre_nuevo or nombre_actual} actualizados"}

@app.post("/api/delete_person")
async def delete_person(
    nombre: str = Form(...),
    autorizacion: UploadFile = File(...),
    user=Depends(require_role(["admin"]))
):
    # 1. Guardar la evidencia/autorización
    auth_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../autorizaciones'))
    os.makedirs(auth_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_filename = autorizacion.filename.replace(" ", "_")
    auth_path = os.path.join(auth_dir, f"auth_{nombre}_{timestamp}_{safe_filename}")
    
    with open(auth_path, "wb") as buffer:
        buffer.write(await autorizacion.read())
        
    # 2. Eliminar de metadata
    metadata = cargar_metadata()
    if nombre in metadata:
        del metadata[nombre]
        guardar_metadata(metadata)
        
    # 3. Eliminar foto física
    ruta_fotos = os.path.abspath(os.path.join(os.path.dirname(__file__), '../fotos'))
    for ext in ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']:
        file_path = os.path.join(ruta_fotos, f"{nombre}{ext}")
        if os.path.exists(file_path):
            os.remove(file_path)
            break
            
    # 4. Reentrenar la IA sin esta persona
    global encodings_db, nombres_db
    encodings_db, nombres_db = cargar_rostros()
    
    logger.warning(f"🗑️ Persona eliminada: {nombre} por {user['username']}. Autorización guardada en: {auth_path}")
    return {"status": "success", "message": f"{nombre} ha sido eliminado definitivamente del sistema."}

@app.post("/api/upload_person")
async def upload_person(
    nombre: str = Form(...),
    edad: int = Form(...),
    peligrosidad: str = Form(...),
    accion: str = Form(...),
    foto: UploadFile = File(...),
    user = Depends(require_role(["admin", "guardia"]))
):
    ruta_fotos = os.path.abspath(os.path.join(os.path.dirname(__file__), '../fotos'))
    os.makedirs(ruta_fotos, exist_ok=True)
    
    file_path = os.path.join(ruta_fotos, f"{nombre}.jpg")
    with open(file_path, "wb") as buffer:
        buffer.write(await foto.read())
        
    metadata = cargar_metadata()
    metadata[nombre] = {"edad": edad, "peligrosidad": peligrosidad, "accion": accion}
    guardar_metadata(metadata)
    
    global encodings_db, nombres_db
    encodings_db, nombres_db = cargar_rostros()
    
    logger.info(f"Nueva persona registrada via web: {nombre}")
    return {"status": "success", "message": f"{nombre} registrado y base de datos actualizada"}

@app.get("/api/logs")
async def get_logs(lines: int = 100, user=Depends(require_role(["admin"]))):
    if not os.path.exists(log_file_path):
        return {"logs": "El archivo de log no existe aún."}
    try:
        with open(log_file_path, "r") as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:]
            return {"logs": "".join(last_lines)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer el log: {e}")

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
