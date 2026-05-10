import streamlit as st
import cv2
import face_recognition
import numpy as np
import os
import time
import pandas as pd
import requests
import logging
from datetime import datetime, timedelta

# --- 📝 CONFIGURACIÓN DE LOGS ---
# Configurar el sistema de logging para guardar eventos en un archivo
logging.basicConfig(
    filename='sistema_vigilancia.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.info("=== Iniciando Sistema de Vigilancia Pro ===")

# --- 🔐 CONFIGURACIÓN DE SEGURIDAD (Tus credenciales validadas) ---
TELEGRAM_TOKEN = "8737879930:AAHBqVqTvEHS-sXsSQyFG-xfwboottjFjYw"
TELEGRAM_CHAT_ID = "5835369596"
ARCHIVO_HISTORICO = "historial_seguridad_poc.csv"

# --- 📂 INICIALIZACIÓN DE SISTEMA ---
st.set_page_config(page_title="Vigilancia Inteligente Pro", layout="wide")
st.title("🛡️ Protocolo de Seguridad: Protección y Escalamiento")

# --- 🎨 INYECCIÓN DE TAILWIND CSS ---
st.markdown("""
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
""", unsafe_allow_html=True)

def inicializar_archivo():
    if not os.path.exists(ARCHIVO_HISTORICO):
        df = pd.DataFrame(columns=["Nombre", "Fecha", "Hora", "Datetime"])
        df.to_csv(ARCHIVO_HISTORICO, index=False)

inicializar_archivo()

# --- SIDEBAR: CONFIGURACIÓN DE INTELIGENCIA ---
st.sidebar.header("⚙️ Ajustes de Inteligencia")

# 1. Regulador de tiempo de enfriamiento (Antes era fijo de 3 min, ahora es ajustable)
minutos_enfriamiento = st.sidebar.slider(
    "Enfriamiento entre registros (min)", 
    min_value=1, 
    max_value=30, 
    value=3  # Valor por defecto, se ajustará más adelante
)

# 2. Umbral de Alerta (Cuántas veces para disparar Telegram)
umbral_alerta = st.sidebar.number_input(
    "Umbral de registros para Alerta", 
    min_value=1, 
    value=3 # Valor por defecto, se ajustará más adelante
)

# 3. Interruptor Maestro de Alertas
alertas_activas = st.sidebar.toggle("🔔 Activar Notificaciones Telegram", value=True)

# 4. Botón de Reinicio de Sesión (Limpia los contadores del día)
if st.sidebar.button("🗑️ Limpiar Contadores Actuales", use_container_width=True):
    st.session_state.registro_tiempos = {}
    st.toast("Contadores reiniciados", icon="🧹")

# --- 📨 MOTOR DE NOTIFICACIONES TELEGRAM ---
def enviar_alerta_telegram(nombre, conteo):
    mensaje = (
        f"🚨 <b>ALERTA DE SEGURIDAD CRÍTICA</b> 🚨\n\n"
        f"<b>Sujeto detectado:</b> {nombre}\n"
        f"<b>Incidencia:</b> Detectado {conteo} veces en menos de 10 minutos.\n"
        f"<b>Hora del reporte:</b> {datetime.now().strftime('%H:%M:%S')}\n"
        f"<i>⚠️ Acción: Se recomienda verificar cámaras o avisar a seguridad.</i>"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status() # Lanza excepción si el status no es 200 OK
        logging.info(f"Alerta de Telegram enviada exitosamente para: {nombre} (conteo: {conteo})")
    except Exception as e:
        error_msg = f"Error al enviar Telegram: {e}"
        logging.error(error_msg)
        st.error(error_msg)

# --- 🧠 LÓGICA DE INTELIGENCIA (Escalamiento) ---
def procesar_seguridad_poc(nombre):
    if nombre == "Desconocido":
        return

    ahora = datetime.now()
    timestamp_actual = ahora.timestamp()
    
    if 'registro_tiempos' not in st.session_state:
        st.session_state.registro_tiempos = {}
    
    ultima_vez = st.session_state.registro_tiempos.get(nombre, 0)
    
    # REGLA PoC PRUEBAS: Enfriamiento de 1 minuto
    segundos_enfriamiento = minutos_enfriamiento * 60 

    if (timestamp_actual - ultima_vez) > segundos_enfriamiento:
        # 1. Guardar en CSV para auditoría
        nuevo_reg = {
            "Nombre": nombre,
            "Fecha": ahora.strftime("%Y-%m-%d"),
            "Hora": ahora.strftime("%H:%M:%S"),
            "Datetime": ahora.strftime("%Y-%m-%d %H:%M:%S")
        }
        pd.DataFrame([nuevo_reg]).to_csv(ARCHIVO_HISTORICO, mode='a', header=False, index=False)
        
        # 2. Actualizar memoria de sesión
        st.session_state.registro_tiempos[nombre] = timestamp_actual
        st.toast(f"✅ Registro guardado en historial: {nombre}", icon="💾")

        # 3. Análisis de Reincidencia (¿umbral_alerta registros en X min?)
        df_h = pd.read_csv(ARCHIVO_HISTORICO)
        df_h['Datetime'] = pd.to_datetime(df_h['Datetime'])
        hace_ventana_riesgo = ahora - timedelta(minutes=minutos_enfriamiento) # Usamos el mismo enfriamiento para la ventana de riesgo
        
        # Filtrar registros de esta persona en la ventana de tiempo
        registros_recientes = df_h[(df_h['Nombre'] == nombre) & (df_h['Datetime'] > hace_ventana_riesgo)]
        conteo_total = len(registros_recientes)

        # 4. Disparar Alerta si se cumple el patrón de riesgo
        if conteo_total >= umbral_alerta:
            if alertas_activas:
                enviar_alerta_telegram(nombre, conteo_total)
            st.error(f"🚨 ESCALAMIENTO ACTIVO: {nombre} detectado {conteo_total} veces. Alerta enviada.", icon="📲")

@st.dialog("Tarjetas de Identidad Confirmada")
def mostrar_tarjetas_emergentes():
    if os.path.exists(ARCHIVO_HISTORICO):
        df_stat = pd.read_csv(ARCHIVO_HISTORICO)
        if not df_stat.empty:
            df_conocidos = df_stat[df_stat['Nombre'] != 'Desconocido']
            conteo = df_conocidos['Nombre'].value_counts().reset_index()
            conteo.columns = ['Persona', 'Total Detecciones']
            
            html_cards = '<div class="flex flex-col gap-4">'
            for _, row in conteo.iterrows():
                html_cards += f"""
<div class="bg-gray-800 border-l-4 border-green-500 rounded-lg shadow-lg p-4 flex items-center justify-between">
<div class="flex items-center gap-4">
<div class="bg-gray-700 rounded-full p-3">
<svg class="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
</div>
<div>
<h4 class="text-white font-bold text-lg m-0">{row['Persona']}</h4>
<p class="text-gray-400 text-xs m-0 mt-1 uppercase tracking-wider">Identidad Confirmada</p>
</div>
</div>
<div class="bg-gray-900 rounded px-4 py-2 text-center shadow-inner">
<span class="text-3xl font-black text-green-400 leading-none">{row['Total Detecciones']}</span>
<p class="text-[10px] text-gray-500 uppercase tracking-widest mt-1">Veces</p>
</div>
</div>
"""
            html_cards += '</div>'
            st.markdown(html_cards, unsafe_allow_html=True)
            if st.button("Cerrar Ventana"):
                st.rerun()
        else:
            st.info("No hay registros de identidades confirmadas aún.")
    else:
        st.info("El historial de seguridad está vacío.")

# --- 🛠️ CARGA DE BASE DE DATOS DE ROSTROS ---
def cargar_rostros():
    logging.info("Iniciando carga de base de datos de rostros...")
    ruta_fotos = "/Applications/XAMPP/xamppfiles/htdocs/camara/fotos/"
    conocidos_encodings = []
    conocidos_nombres = []
    
    if not os.path.exists(ruta_fotos):
        error_msg = f"Carpeta de fotos no encontrada en: {ruta_fotos}"
        logging.error(error_msg)
        st.error(error_msg)
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
                    logging.info(f"Rostro cargado exitosamente: {archivo}")
                else:
                    logging.warning(f"No se encontró un rostro en la imagen: {archivo}")
            except Exception as e:
                error_msg = f"Error cargando {archivo}: {e}"
                logging.error(error_msg)
                st.sidebar.error(error_msg)
                
    logging.info(f"Carga finalizada. {len(conocidos_encodings)} rostros cargados de {archivos_procesados} archivos válidos procesados.")
    return conocidos_encodings, conocidos_nombres

encodings_db, nombres_db = cargar_rostros()

# --- 📹 BUCLE DE VIDEO Y MONITOREO ---
st.sidebar.divider()
if st.sidebar.toggle("▶️ Iniciar Sistema de Vigilancia", value=False):
    if not encodings_db:
        st.warning("⚠️ No hay fotos cargadas. Se detectará a todos como 'Desconocido'.")
    if True: # Se cambia 'else' por 'if True' para permitir iniciar la cámara sin base de datos
        # Layout con dos columnas: Video a la izquierda, Dashboard a la derecha
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("### 📷 Feed en Vivo")
            frame_window = st.image([])
        with col2:
            st.markdown("### 📊 Panel de Control")
            # Espacios para métricas rápidas
            metrica_total = st.empty()
            st.markdown("---")
            
            # Controles para alternar la vista
            col_dash1, col_dash2 = st.columns([1, 1])
            with col_dash1:
                st.markdown("#### Detalle")
            with col_dash2:
                if st.button("Ver Tarjetas Avanzadas", use_container_width=True):
                    mostrar_tarjetas_emergentes()
                
            stats_window = st.empty()

        cap = cv2.VideoCapture(0) # Cámara local del Mac
        frame_count = 0
        
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret: 
                    time.sleep(0.1) # Pausa breve para esperar a que la cámara encienda
                    continue
                
                frame_count += 1
                frame = cv2.flip(frame, 1) # Efecto espejo
                
                # --- PROCESAMIENTO (Línea 107 Corregida) ---
                # Reducimos el tamaño para mejorar los FPS
                small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
                rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                
                face_locs = face_recognition.face_locations(rgb_small_frame)
                face_encs = face_recognition.face_encodings(rgb_small_frame, face_locs)

                for (top, right, bottom, left), face_enc in zip(face_locs, face_encs):
                    # Comparar con la base de datos usando la distancia mínima (más preciso)
                    face_distances = face_recognition.face_distance(encodings_db, face_enc)
                    nombre = "Desconocido"
                    color = (0, 0, 255) # Rojo para desconocidos

                    if len(face_distances) > 0:
                        best_match_index = np.argmin(face_distances)
                        # Tolerancia más estricta: 0.5 (menor valor = más similitud)
                        if face_distances[best_match_index] <= 0.5:
                            nombre = nombres_db[best_match_index]
                            color = (0, 255, 0) # Verde para conocidos
                    
                    # --- DISPARAR LÓGICA DE SEGURIDAD ---
                    procesar_seguridad_poc(nombre)
                    
                    # Escalar coordenadas de vuelta al tamaño original
                    top *= 4; right *= 4; bottom *= 4; left *= 4
                    cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                    cv2.putText(frame, nombre, (left, top-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

                # Mostrar el frame en la interfaz de Streamlit
                frame_window.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), use_column_width=True)
                
                # Actualizar Dashboard de Estadísticas periódicamente (cada ~30 frames)
                if frame_count % 30 == 0:
                    try:
                        if os.path.exists(ARCHIVO_HISTORICO):
                            df_stat = pd.read_csv(ARCHIVO_HISTORICO)
                            if not df_stat.empty:
                                # Filtrar 'Desconocido' antes de contar
                                df_conocidos = df_stat[df_stat['Nombre'] != 'Desconocido']

                                # Actualizar métrica total (solo conocidos)
                                total_eventos = len(df_conocidos)
                                metrica_total.metric(label="Total Eventos Registrados (Conocidos)", value=total_eventos)
                                
                                # Actualizar tabla de detalle (solo conocidos)
                                conteo = df_conocidos['Nombre'].value_counts().reset_index()
                                conteo.columns = ['Persona', 'Total Detecciones']
                                
                                # Usamos st.dataframe con configuraciones para que se vea mejor en el tema oscuro
                                stats_window.dataframe(
                                    conteo, 
                                    use_container_width=True, 
                                    hide_index=True
                                )
                    except Exception as e_dashboard:
                        logging.error(f"Error actualizando dashboard: {e_dashboard}")
        except Exception as e_main:
            error_msg = f"Error crítico en el bucle principal de video: {e_main}"
            logging.critical(error_msg)
            st.error(error_msg)
        finally:
            cap.release()
            logging.info("Cámara liberada y bucle de video finalizado.")
else:
    st.info("Sistema listo. Presiona el botón en la barra lateral para iniciar el monitoreo.")