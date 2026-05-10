import cv2

import face_recognition # Librería estándar de reconocimiento



# Configuración de tu Reolink

url = "rtsp://admin:TU_PASSWORD@192.168.100.182:9000/h264Preview_01_main"

video_capture = cv2.VideoCapture(url)



while True:

    ret, frame = video_capture.read()

    

    # Reducir el tamaño para que el procesamiento sea veloz

    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)

    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)



    # Lógica de detección

    face_locations = face_recognition.face_locations(rgb_small_frame)



    # Dibujar la "interfaz" sobre el video

    for (top, right, bottom, left) in face_locations:

        top *= 4; right *= 4; bottom *= 4; left *= 4 # Volver al tamaño original

        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)

        cv2.putText(frame, "Persona Detectada", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)



    # Mostrar la ventana

    cv2.imshow('Software de Reconocimiento - PoC', frame)



    if cv2.waitKey(1) & 0xFF == ord('q'):

        break



video_capture.release()

cv2.destroyAllWindows()