import cv2
import time
import subprocess
from datetime import datetime
from pathlib import Path
import streamlit as st
import numpy as np
from ultralytics import YOLO

PERSON_MODEL_PATH = "models/yolo26m.pt"
EPP_MODEL_PATH    = "models/final/epp_production/model_epp_v26.pt"
BASE_OUTPUT       = Path("/workspaces/deteccioneppalimentarias/data/raw/tec_teziutlan/session_lab_alimentos")

IMGSZ       = 640
CONF_PERSON = 0.4
CONF_EPP    = 0.3

RESOLUCIONES = [
    (640, 480),
    (320, 240),
    (160, 120),
]

PERSON_NAMES = {0: "persona"}

EPP_NAMES = {
    1:  "guante",
    2:  "no_guante",
    3:  "gafas",
    4:  "no_gafas",
    5:  "gorro",
    6:  "no_gorro",
    7:  "bata",
    8:  "no_bata",
    9:  "mascarilla",
    10: "no_mascarilla",
    11: "pantalón",
    12: "no_pantalón",
    13: "botas",
    14: "no_botas",
}

PERSON_COLOR = (255, 0, 0)

EPP_COLORS = {
    1:  (0, 0, 200),
    2:  (0, 100, 200),
    3:  (0, 200, 0),
    4:  (0, 150, 150),
    5:  (200, 0, 200),
    6:  (150, 0, 150),
    7:  (200, 200, 0),
    8:  (100, 100, 0),
    9:  (200, 0, 100),
    10: (150, 0, 80),
    11: (0, 165, 255),
    12: (0, 100, 200),
    13: (128, 0, 128),
    14: (80, 0, 80),
}


def add_timestamp(frame):
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S Laboratorio de Quimica")
    font  = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(ahora, font, 0.6, 1)
    cv2.rectangle(frame, (5, 5), (5 + tw + 4, 5 + th + 4), (0, 0, 0), -1)
    cv2.putText(frame, ahora, (7, 5 + th), font, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


def apply_clahe(frame):
    lab     = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe   = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l       = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def draw_detections(frame, results_person, results_epp):
    annotated = frame.copy()

    if results_person is not None and len(results_person) > 0:
        for box in results_person[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            conf = box.conf[0].item()
            cls  = int(box.cls[0])
            if cls == 0:
                label = f"{PERSON_NAMES[cls]} {conf:.2f}"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), PERSON_COLOR, 2)
                cv2.rectangle(annotated, (x1, y1 - th - 4), (x1 + tw + 4, y1), PERSON_COLOR, -1)
                cv2.putText(annotated, label, (x1 + 2, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    if results_epp is not None and len(results_epp) > 0:
        for box in results_epp[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            conf  = box.conf[0].item()
            cls   = int(box.cls[0])
            label = EPP_NAMES.get(cls, f"clase_{cls}")
            color = EPP_COLORS.get(cls, (100, 100, 100))
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.rectangle(annotated, (x1, y1 - th - 4), (x1 + tw + 4, y1), color, -1)
            cv2.putText(annotated, label, (x1 + 2, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    return annotated


@st.cache_resource
def load_models():
    model_person = YOLO(PERSON_MODEL_PATH)
    model_epp    = YOLO(EPP_MODEL_PATH)
    return model_person, model_epp

model_person, model_epp = load_models()


def init_camera(device_idx, formato):
    fourcc_map = {
        'MJPG': cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'),
        'YUYV': cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V'),
    }
    fourcc = fourcc_map.get(formato)
    if fourcc is None:
        return None

    # probar primero el índice elegido, luego fallbacks
    indices = list(dict.fromkeys([device_idx, 0, 1, 2, 3]))

    for idx in indices:
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            continue

        for width, height in RESOLUCIONES:
            cap.set(cv2.CAP_PROP_FOURCC, fourcc)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_CONVERT_RGB, 1)

            actual_w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps   = cap.get(cv2.CAP_PROP_FPS)
            raw_fourcc   = int(cap.get(cv2.CAP_PROP_FOURCC))
            fourcc_str   = ''.join(chr((raw_fourcc >> i) & 0xFF) for i in (0, 8, 16, 24))
            print(f"cámara {idx} → {actual_w}x{actual_h} {actual_fps}fps {fourcc_str}")

            for attempt in range(3):
                ret, frame = cap.read()
                if ret and frame is not None:
                    return cap
                time.sleep(0.3)

        cap.release()

    return None


# ---- session state ----

defaults = {
    'capturando':     False,
    'intervalo':      3,
    'clase':          'guantes',
    'contador':       0,
    'ultima_captura': time.time(),
    'frame_actual':   None,
    'last_results':   (None, None),
    'cap':            None,
    'device_idx':     0,
    'camera_ok':      False,
    'formato':        'MJPG',
    'use_clahe':      False,
    'is_negative':    False,
    'conf_pos':       0.15,
    'conf_neg':       0.05,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def guardar_captura(frame_original, results, clase, is_negative, use_clahe):
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    tipo      = "neg" if is_negative else "pos"
    base_name = f"{clase}_{tipo}_{ts}"

    output_dir = BASE_OUTPUT / f"sesion_{datetime.now().strftime('%Y%m%d')}" / clase
    output_dir.mkdir(parents=True, exist_ok=True)

    original_path  = output_dir / f"{base_name}.jpg"
    annotated_path = output_dir / f"{base_name}_annotated.jpg"
    labels_path    = output_dir / f"{base_name}.txt"

    frame_to_save = frame_original.copy()
    if use_clahe:
        frame_to_save = apply_clahe(frame_to_save)

    cv2.imwrite(str(original_path),  add_timestamp(frame_to_save))
    cv2.imwrite(str(annotated_path), add_timestamp(draw_detections(frame_to_save, *results)))

    results_person, results_epp = results
    with open(labels_path, 'w') as f:
        if not is_negative:
            if results_person is not None and len(results_person) > 0:
                for box in results_person[0].boxes:
                    cls  = int(box.cls[0])
                    xywh = box.xywhn[0].tolist()
                    f.write(f"{cls} {xywh[0]:.6f} {xywh[1]:.6f} {xywh[2]:.6f} {xywh[3]:.6f}\n")
            if results_epp is not None and len(results_epp) > 0:
                for box in results_epp[0].boxes:
                    cls  = int(box.cls[0])
                    xywh = box.xywhn[0].tolist()
                    f.write(f"{cls} {xywh[0]:.6f} {xywh[1]:.6f} {xywh[2]:.6f} {xywh[3]:.6f}\n")
        # negativos: archivo vacío a propósito

    st.session_state.contador += 1
    return original_path, annotated_path, labels_path


def infer_and_draw(frame, use_clahe):
    frame_infer = apply_clahe(frame) if use_clahe else frame

    results_person = model_person(frame_infer, conf=CONF_PERSON, classes=[0], imgsz=IMGSZ, verbose=False, half=True)
    results_epp    = model_epp(frame_infer, conf=CONF_EPP, imgsz=IMGSZ, verbose=False, half=True)

    return draw_detections(frame_infer, results_person, results_epp), (results_person, results_epp)


def reentrenar():
    cmd = ["python", "notebooks/retrain.py", "--epochs", "20", "--batch", "8", "--imgsz", "640"]
    try:
        with st.spinner("Reentrenando modelo... (puede tomar varios minutos)"):
            subprocess.run(cmd, check=True)
        st.success("Reentrenamiento completado")
    except subprocess.CalledProcessError as e:
        st.error(f"Error: {e}")


# ---- interfaz ----

st.set_page_config(page_title="Captura con detección EPP", layout="wide")
st.title("🛡️ Captura de imágenes con detección de personas y EPP (cámara local)")

with st.sidebar:
    st.header("Controles")

    device_idx = st.number_input("Índice de cámara", min_value=0, max_value=10,
                                 value=st.session_state.device_idx, step=1)
    if device_idx != st.session_state.device_idx:
        st.session_state.device_idx = device_idx
        if st.session_state.cap:
            st.session_state.cap.release()
        st.session_state.cap       = None
        st.session_state.camera_ok = False

    formato = st.selectbox("Formato", ["MJPG", "YUYV"],
                           index=0 if st.session_state.formato == "MJPG" else 1)
    if formato != st.session_state.formato:
        st.session_state.formato = formato
        if st.session_state.cap:
            st.session_state.cap.release()
        st.session_state.cap       = None
        st.session_state.camera_ok = False

    if st.button("🔌 Conectar cámara"):
        if st.session_state.cap:
            st.session_state.cap.release()
        st.session_state.cap       = init_camera(st.session_state.device_idx, st.session_state.formato)
        st.session_state.camera_ok = st.session_state.cap is not None
        if st.session_state.camera_ok:
            st.success("Cámara conectada correctamente")
        else:
            st.error("No se pudo conectar a ninguna cámara")

    st.markdown("---")

    st.session_state.clase       = st.text_input("Clase a capturar", value=st.session_state.clase)
    st.session_state.use_clahe   = st.checkbox("Usar CLAHE (mejora contraste)",               value=st.session_state.use_clahe)
    st.session_state.is_negative = st.checkbox("Capturar como ejemplo negativo (sin etiquetas)", value=st.session_state.is_negative)

    st.markdown("#### Umbrales de confianza")
    st.session_state.conf_pos = st.slider("Clases positivas (guante, gafas...)",      0.0, 1.0, st.session_state.conf_pos, 0.01)
    st.session_state.conf_neg = st.slider("Clases negativas (no_guante, no_gafas...)", 0.0, 1.0, st.session_state.conf_neg, 0.01)

    st.session_state.intervalo = st.slider("Intervalo (segundos)", 1, 10, st.session_state.intervalo)

    if st.button("⏯️ Pausar/Reanudar"):
        st.session_state.capturando = not st.session_state.capturando
        if st.session_state.capturando:
            st.session_state.ultima_captura = time.time()

    if st.button("📸 Capturar manual"):
        if st.session_state.frame_actual is not None and st.session_state.last_results != (None, None):
            orig, ann, lbl = guardar_captura(
                st.session_state.frame_actual,
                st.session_state.last_results,
                st.session_state.clase,
                st.session_state.is_negative,
                st.session_state.use_clahe,
            )
            tipo = "negativo" if st.session_state.is_negative else "positivo"
            st.success(f"Capturada ({tipo}) en {st.session_state.clase}: {orig.name}")
        else:
            st.warning("No hay frame disponible")

    estado = "▶️ CAPTURANDO" if st.session_state.capturando else "⏸️ PAUSADO"
    st.metric("Estado",          estado)
    st.metric("Fotos capturadas", st.session_state.contador)
    st.metric("Intervalo",        f"{st.session_state.intervalo} s")

col1, col2 = st.columns([3, 1])
with col1:
    video_placeholder = st.empty()
with col2:
    st.subheader("Instrucciones")
    st.markdown("""
    - Conecta la cámara.
    - Especifica la clase a capturar.
    - **CLAHE** mejora contraste.
    - **Negativo** guarda sin etiquetas (útil para ausencias).
    - Ajusta umbrales según necesites.
    - Captura manual o automática.
    - Las imágenes se guardan en `data/raw/tec_teziutlan/session_lab_alimentos/[fecha]/[clase]/`.
    """)
    if not st.session_state.camera_ok:
        st.warning("⚠️ Cámara no conectada")

if not st.session_state.camera_ok:
    st.stop()


# ---- bucle principal ----

cap         = st.session_state.cap
frame_count = 0
error_count = 0
max_errors  = 10

while True:
    try:
        ret, frame = cap.read()
        if not ret:
            error_count += 1
            if error_count > max_errors:
                st.error("⚠️ Se perdió la conexión con la cámara")
                cap.release()
                st.session_state.camera_ok = False
                st.rerun()
            else:
                time.sleep(0.1)
                continue
        else:
            error_count  = 0
            frame_count += 1
            if frame_count % 30 == 0:
                print(f"frame #{frame_count}")

        frame_annotated, results = infer_and_draw(frame, st.session_state.use_clahe)
        st.session_state.frame_actual = frame.copy()
        st.session_state.last_results = results

        frame_rgb = cv2.cvtColor(add_timestamp(frame_annotated), cv2.COLOR_BGR2RGB)
        video_placeholder.image(frame_rgb, channels="RGB", use_container_width=True)

        ahora = time.time()
        if st.session_state.capturando and (ahora - st.session_state.ultima_captura) >= st.session_state.intervalo:
            guardar_captura(
                frame, results,
                st.session_state.clase,
                st.session_state.is_negative,
                st.session_state.use_clahe,
            )
            st.session_state.ultima_captura = ahora
            st.toast(f"Captura automática #{st.session_state.contador}")

        time.sleep(0.01)

    except Exception as e:
        st.error(f"Error inesperado: {e}")
        print(f"excepción: {e}")
        time.sleep(1)