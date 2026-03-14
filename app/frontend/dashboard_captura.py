import cv2
import time
import subprocess
import requests
import os
from datetime import datetime
from pathlib import Path
import streamlit as st
import numpy as np

# ========== CONFIGURACIÓN ==========
API_URL = os.getenv("API_URL", "http://backend:5000")
DATA_DIR = Path("/workspaces/deteccioneppalimentarias/data")
TRAIN_IMAGES_DIR = DATA_DIR / "train" / "images"
TRAIN_LABELS_DIR = DATA_DIR / "train" / "labels"
VAL_IMAGES_DIR = DATA_DIR / "val" / "images"
VAL_LABELS_DIR = DATA_DIR / "val" / "labels"
NOTEBOOKS_DIR = Path("/workspaces/deteccioneppalimentarias/notebooks")

for d in [TRAIN_IMAGES_DIR, TRAIN_LABELS_DIR, VAL_IMAGES_DIR, VAL_LABELS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

CONF_PERSON = 0.4

RESOLUCIONES = [
    (640, 480),
    (320, 240),
    (160, 120)
]

PERSON_NAMES = {0: "persona"}

EPP_NAMES = {
    1: "guante",
    2: "no_guante",
    3: "gafas",
    4: "no_gafas",
    5: "gorro",
    6: "no_gorro",
    7: "bata",
    8: "no_bata",
    9: "mascarilla",
    10: "no_mascarilla",
    11: "pantalón",
    12: "no_pantalón",
    13: "botas",
    14: "no_botas"
}

PERSON_COLOR = (255, 0, 0)

EPP_COLORS = {
    1: (0, 0, 200),
    2: (0, 100, 200),
    3: (0, 200, 0),
    4: (0, 150, 150),
    5: (200, 0, 200),
    6: (150, 0, 150),
    7: (200, 200, 0),
    8: (100, 100, 0),
    9: (200, 0, 100),
    10: (150, 0, 80),
    11: (0, 165, 255),
    12: (0, 100, 200),
    13: (128, 0, 128),
    14: (80, 0, 80)
}

def add_timestamp(frame):
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S Laboratorio de Quimica")
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    color = (255, 255, 255)
    thickness = 1
    (text_w, text_h), _ = cv2.getTextSize(ahora, font, font_scale, thickness)
    cv2.rectangle(frame, (5, 5), (5 + text_w + 4, 5 + text_h + 4), (0, 0, 0), -1)
    cv2.putText(frame, ahora, (7, 5 + text_h), font, font_scale, color, thickness, cv2.LINE_AA)
    return frame

def apply_clahe(frame):
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    l = clahe.apply(l)
    enhanced = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    return enhanced

def call_api(frame):
    _, img_encoded = cv2.imencode('.jpg', frame)
    files = {'image': ('frame.jpg', img_encoded.tobytes(), 'image/jpeg')}
    try:
        response = requests.post(f"{API_URL}/detect", files=files, timeout=0.5)
        if response.status_code == 200:
            data = response.json()
            print(f"API respondió con {len(data['detections'])} detecciones")
            return data['detections']
        else:
            print(f"API error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Error en API: {e}")
    return []

def draw_detections(frame, person_detections, epp_detections):
    annotated = frame.copy()

    # Personas
    for det in person_detections:
        conf = float(det['conf'])
        if conf < CONF_PERSON:
            continue
        x1, y1, x2, y2 = map(int, det['bbox'])
        cls = det['cls']
        label = f"{PERSON_NAMES[cls]} {conf:.2f}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), PERSON_COLOR, 2)
        (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x1, y1 - text_h - 4), (x1 + text_w + 4, y1), PERSON_COLOR, -1)
        cv2.putText(annotated, label, (x1 + 2, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    # EPP
    for det in epp_detections:
        conf = float(det['conf'])
        cls = det['cls']
        if cls % 2 == 0:
            if conf < float(st.session_state.conf_neg):
                continue
        else:
            if conf < float(st.session_state.conf_pos):
                continue
        x1, y1, x2, y2 = map(int, det['bbox'])
        label = EPP_NAMES.get(cls, f"clase_{cls}")
        color = EPP_COLORS.get(cls, (100, 100, 100))
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x1, y1 - text_h - 4), (x1 + text_w + 4, y1), color, -1)
        cv2.putText(annotated, label, (x1 + 2, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    return annotated

def init_camera(device_idx, formato):
    if formato == 'MJPG':
        fourcc = cv2.VideoWriter_fourcc('M','J','P','G')
    elif formato == 'YUYV':
        fourcc = cv2.VideoWriter_fourcc('Y','U','Y','V')
    else:
        return None

    indices = [device_idx, 0, 1, 2, 3]
    indices_unicos = []
    for idx in indices:
        if idx not in indices_unicos:
            indices_unicos.append(idx)

    for idx in indices_unicos:
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            continue
        for width, height in RESOLUCIONES:
            cap.set(cv2.CAP_PROP_FOURCC, fourcc)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            for _ in range(3):
                ret, frame = cap.read()
                if ret and frame is not None:
                    return cap
                time.sleep(0.3)
        cap.release()
    return None

# ========== VARIABLES DE ESTADO ==========
if 'capturando' not in st.session_state:
    st.session_state.capturando = False
if 'intervalo' not in st.session_state:
    st.session_state.intervalo = 3
if 'destino' not in st.session_state:
    st.session_state.destino = "train"
if 'contador' not in st.session_state:
    st.session_state.contador = 0
if 'ultima_captura' not in st.session_state:
    st.session_state.ultima_captura = time.time()
if 'frame_actual' not in st.session_state:
    st.session_state.frame_actual = None
if 'last_results' not in st.session_state:
    st.session_state.last_results = ([], [])
if 'cap' not in st.session_state:
    st.session_state.cap = None
if 'device_idx' not in st.session_state:
    st.session_state.device_idx = 0
if 'camera_ok' not in st.session_state:
    st.session_state.camera_ok = False
if 'formato' not in st.session_state:
    st.session_state.formato = "MJPG"
if 'use_clahe' not in st.session_state:
    st.session_state.use_clahe = False
if 'is_negative' not in st.session_state:
    st.session_state.is_negative = False
if 'conf_pos' not in st.session_state:
    st.session_state.conf_pos = 0.15
if 'conf_neg' not in st.session_state:
    st.session_state.conf_neg = 0.05
if 'detecciones_actuales' not in st.session_state:
    st.session_state.detecciones_actuales = 0

def guardar_captura(frame_original, results, destino, is_negative, use_clahe):
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    tipo = "neg" if is_negative else "pos"
    base_name = f"{destino}_{tipo}_{timestamp_str}"

    img_dir = TRAIN_IMAGES_DIR if destino == "train" else VAL_IMAGES_DIR
    lbl_dir = TRAIN_LABELS_DIR if destino == "train" else VAL_LABELS_DIR

    original_path = img_dir / f"{base_name}.jpg"
    annotated_path = img_dir / f"{base_name}_annotated.jpg"
    labels_path = lbl_dir / f"{base_name}.txt"

    frame_to_save = frame_original.copy()
    if use_clahe:
        frame_to_save = apply_clahe(frame_to_save)

    frame_orig_time = add_timestamp(frame_to_save)
    cv2.imwrite(str(original_path), frame_orig_time)

    person_det, epp_det = results
    frame_annotated = draw_detections(frame_to_save, person_det, epp_det)
    frame_ann_time = add_timestamp(frame_annotated)
    cv2.imwrite(str(annotated_path), frame_ann_time)

    if not is_negative:
        with open(labels_path, 'w') as f:
            # Personas
            for det in person_det:
                conf = float(det['conf'])
                if conf < CONF_PERSON:
                    continue
                cls = det['cls']
                x1, y1, x2, y2 = det['bbox']
                h, w = frame_original.shape[:2]
                x_center = (x1 + x2) / 2 / w
                y_center = (y1 + y2) / 2 / h
                width = (x2 - x1) / w
                height = (y2 - y1) / h
                f.write(f"{cls} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")
            # EPP
            for det in epp_det:
                conf = float(det['conf'])
                cls = det['cls']
                if cls % 2 == 0:
                    if conf < float(st.session_state.conf_neg):
                        continue
                else:
                    if conf < float(st.session_state.conf_pos):
                        continue
                x1, y1, x2, y2 = det['bbox']
                h, w = frame_original.shape[:2]
                x_center = (x1 + x2) / 2 / w
                y_center = (y1 + y2) / 2 / h
                width = (x2 - x1) / w
                height = (y2 - y1) / h
                f.write(f"{cls} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")
    else:
        with open(labels_path, 'w') as f:
            pass

    st.session_state.contador += 1
    return original_path, annotated_path, labels_path

def infer_and_draw(frame, use_clahe):
    frame_infer = frame
    if use_clahe:
        frame_infer = apply_clahe(frame)

    detections = call_api(frame_infer)
    # Normalizar tipos
    for d in detections:
        d['cls'] = int(d['cls'])
        d['conf'] = float(d['conf'])

    person_det = [d for d in detections if d['cls'] == 0]
    epp_det = [d for d in detections if d['cls'] != 0]

    annotated = draw_detections(frame_infer, person_det, epp_det)
    return annotated, (person_det, epp_det)

def reentrenar():
    comando = [
        "python", str(NOTEBOOKS_DIR / "retrain.py"),
        "--epochs", "20",
        "--batch", "8",
        "--imgsz", "640"
    ]
    try:
        with st.spinner("Reentrenando..."):
            subprocess.run(comando, check=True)
        st.success("Reentrenamiento completado")
    except subprocess.CalledProcessError as e:
        st.error(f"Error: {e}")

# ========== INTERFAZ STREAMLIT ==========
st.set_page_config(page_title="Captura EPP", layout="wide")
st.title("🛡️ Captura con detección de personas y EPP")

with st.sidebar:
    st.header("Controles")
    device_idx = st.number_input("Índice de cámara", 0, 10, value=st.session_state.device_idx, step=1)
    if device_idx != st.session_state.device_idx:
        st.session_state.device_idx = device_idx
        if st.session_state.cap:
            st.session_state.cap.release()
        st.session_state.cap = None
        st.session_state.camera_ok = False

    formato = st.selectbox("Formato", ["MJPG", "YUYV"], index=0 if st.session_state.formato == "MJPG" else 1)
    if formato != st.session_state.formato:
        st.session_state.formato = formato
        if st.session_state.cap:
            st.session_state.cap.release()
        st.session_state.cap = None
        st.session_state.camera_ok = False

    if st.button("🔌 Conectar cámara"):
        if st.session_state.cap:
            st.session_state.cap.release()
        st.session_state.cap = init_camera(st.session_state.device_idx, st.session_state.formato)
        st.session_state.camera_ok = st.session_state.cap is not None
        if st.session_state.camera_ok:
            st.success("Cámara conectada")
        else:
            st.error("No se pudo conectar")

    st.markdown("---")
    destino = st.radio("Guardar en:", ["train", "val"], index=0 if st.session_state.destino == "train" else 1)
    if destino != st.session_state.destino:
        st.session_state.destino = destino

    st.session_state.use_clahe = st.checkbox("Usar CLAHE", value=st.session_state.use_clahe)
    st.session_state.is_negative = st.checkbox("Capturar como negativo", value=st.session_state.is_negative)

    st.markdown("#### Umbrales de confianza")
    st.session_state.conf_pos = st.slider("Positivas", 0.0, 1.0, st.session_state.conf_pos, 0.01)
    st.session_state.conf_neg = st.slider("Negativas", 0.0, 1.0, st.session_state.conf_neg, 0.01)

    st.session_state.intervalo = st.slider("Intervalo (s)", 1, 10, st.session_state.intervalo)

    if st.button("⏯️ Pausar/Reanudar"):
        st.session_state.capturando = not st.session_state.capturando
        if st.session_state.capturando:
            st.session_state.ultima_captura = time.time()

    if st.button("📸 Capturar manual"):
        if st.session_state.frame_actual is not None:
            orig, ann, lbl = guardar_captura(
                st.session_state.frame_actual,
                st.session_state.last_results,
                st.session_state.destino,
                st.session_state.is_negative,
                st.session_state.use_clahe
            )
            tipo = "neg" if st.session_state.is_negative else "pos"
            st.success(f"Capturada {tipo} en {st.session_state.destino}: {orig.name}")
        else:
            st.warning("No hay frame")

    estado = "▶️ CAPTURANDO" if st.session_state.capturando else "⏸️ PAUSADO"
    st.metric("Estado", estado)
    st.metric("Fotos", st.session_state.contador)
    st.metric("Intervalo", f"{st.session_state.intervalo} s")

    st.markdown("---")
    if st.button("🧠 Reentrenar"):
        reentrenar()

col1, col2 = st.columns([3, 1])
with col1:
    video_placeholder = st.empty()
with col2:
    st.subheader("Instrucciones")
    st.markdown("Conecta cámara, elige train/val, ajusta umbrales y captura.")
    st.metric("Detecciones en frame", st.session_state.detecciones_actuales)
    st.info("Las detecciones mostradas no se guardan automáticamente.")
    if not st.session_state.camera_ok:
        st.warning("Cámara no conectada")

if not st.session_state.camera_ok:
    st.stop()

# ========== BUCLE PRINCIPAL ==========
cap = st.session_state.cap
frame_count = 0
error_count = 0
max_errors = 10

while True:
    try:
        ret, frame = cap.read()
        if not ret:
            error_count += 1
            if error_count > max_errors:
                st.error("Se perdió conexión con cámara")
                cap.release()
                st.session_state.camera_ok = False
                st.rerun()
            else:
                time.sleep(0.1)
                continue
        error_count = 0
        frame_count += 1

        frame_annotated, results = infer_and_draw(frame, st.session_state.use_clahe)
        st.session_state.frame_actual = frame.copy()
        st.session_state.last_results = results

        total = len(results[0]) + len(results[1])
        st.session_state.detecciones_actuales = total
        if total == 0:
            print("No hay detecciones en este frame")

        frame_with_time = add_timestamp(frame_annotated)
        frame_rgb = cv2.cvtColor(frame_with_time, cv2.COLOR_BGR2RGB)
        video_placeholder.image(frame_rgb, channels="RGB", use_container_width=True)

        ahora = time.time()
        if st.session_state.capturando and (ahora - st.session_state.ultima_captura) >= st.session_state.intervalo:
            guardar_captura(
                frame,
                results,
                st.session_state.destino,
                st.session_state.is_negative,
                st.session_state.use_clahe
            )
            st.session_state.ultima_captura = ahora
            st.toast(f"Auto captura #{st.session_state.contador}")

        time.sleep(0.01)
    except Exception as e:
        import traceback
        st.error(f"Error: {e}")
        traceback.print_exc()
        time.sleep(1)