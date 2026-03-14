import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
from ultralytics import YOLO
import os
import time

app = Flask(__name__)
CORS(app)

# Cargar modelos
print("Cargando modelo de personas...")
model_person = YOLO("/app/backend/models/yolo26m.pt")
print("Modelo de personas cargado")

print("Cargando modelo de EPP...")
model_epp = YOLO("/app/backend/models/modeloepp_v1.pt")
print("Modelo de EPP cargado")

@app.route('/detect', methods=['POST'])
def detect():
    print("Recibida petición /detect")
    
    # Recibir imagen
    file = request.files['image']
    img_bytes = file.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        print("Error: No se pudo decodificar la imagen")
        return jsonify({"detections": []})
    
    print(f"Imagen decodificada, shape: {img.shape}")
    
    # Inferencia con umbrales bajos para prueba
    start = time.time()
    results_person = model_person(img, conf=0.25, classes=[0], imgsz=640, verbose=False, half=True)
    person_time = time.time() - start
    person_count = len(results_person[0].boxes) if results_person and len(results_person) > 0 else 0
    print(f"Personas detectadas: {person_count} (tiempo: {person_time:.3f}s)")
    
    start = time.time()
    results_epp = model_epp(img, conf=0.1, imgsz=640, verbose=False, half=True)
    epp_time = time.time() - start
    epp_count = len(results_epp[0].boxes) if results_epp and len(results_epp) > 0 else 0
    print(f"EPP detectadas: {epp_count} (tiempo: {epp_time:.3f}s)")
    
    detections = []
    # Personas
    if results_person and len(results_person) > 0:
        for box in results_person[0].boxes:
            detections.append({
                "cls": int(box.cls[0]),
                "conf": float(box.conf[0]),
                "bbox": box.xyxy[0].tolist()
            })
    # EPP
    if results_epp and len(results_epp) > 0:
        for box in results_epp[0].boxes:
            detections.append({
                "cls": int(box.cls[0]),
                "conf": float(box.conf[0]),
                "bbox": box.xyxy[0].tolist()
            })
    
    print(f"Total detecciones enviadas: {len(detections)}")
    return jsonify({"detections": detections})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)