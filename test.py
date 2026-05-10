import streamlit as st
import cv2

st.title("Prueba de Webcam")
run = st.checkbox('Iniciar Webcam')
FRAME_WINDOW = st.image([])
camera = cv2.VideoCapture(0) # 0 es la webcam integrada del Mac

while run:
    _, frame = camera.read()
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    FRAME_WINDOW.image(frame)
else:
    st.write('Webcam detenida')