import requests
import json

# --- CONFIGURACIÓN DE TU CÁMARA ---
IP_CAMARA = "192.168.100.182"  # <--- Cambia por la IP real de tu Reolink
USUARIO = "admin"
PASSWORD = "Rafa2422!"     # <--- Tu contraseña de la cámara

# URL para la API de Reolink
#url = f"http://{IP_CAMARA}/cgi-bin/api.cgi?user={USUARIO}&password={PASSWORD}"
# Cambiamos http://{IP} por http://{IP}:9000
url = f"http://{IP_CAMARA}:9000/cgi-bin/api.cgi?user={USUARIO}&password={PASSWORD}"

# Cuerpo del mensaje para activar RTSP y ONVIF
payload = [
    {
        "cmd": "SetNetPort",
        "action": 0,
        "param": {
            "NetPort": {
                "adminPort": 80,
                "rtmpPort": 1935,
                "httpsPort": 443,
                "rtspPort": 554,   # <--- La puerta que necesitamos abierta
                "onvifPort": 9000, # <--- La puerta de comunicación estándar
                "isRtmp": 1,
                "isRtsp": 1,       # 1 significa ACTIVADO
                "isOnvif": 1       # 1 significa ACTIVADO
            }
        }
    }
]

try:
    response = requests.post(url, data=json.dumps(payload))
    print("Respuesta de la cámara:", response.json())
    print("\n✅ Si la respuesta dice 'Success', el puerto RTSP ha sido desbloqueado.")
except Exception as e:
    print(f"❌ Error al conectar: {e}")