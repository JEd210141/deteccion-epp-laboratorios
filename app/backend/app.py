import cv2
import numpy as np
import os
import time
import base64
import threading
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, Response
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

BASE_DIR      = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'static', 'outputs')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

DB_USER     = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST     = os.getenv('DB_HOST')
DB_PORT     = os.getenv('DB_PORT')
DB_NAME     = os.getenv('DB_NAME')

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle':  280,
    'pool_pre_ping': True,
    'pool_size':     5,
    'max_overflow':  10,
}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)


# ---------------------------------------------------------------------------
# Clases del dataset (ORM)
# ---------------------------------------------------------------------------

PERSON_NAMES = {0: 'persona'}

EPP_NAMES = {
    1:  'guante',
    2:  'no_guante',
    3:  'gafas',
    4:  'no_gafas',
    5:  'gorro',
    6:  'no_gorro',
    7:  'bata',
    8:  'no_bata',
    9:  'mascarilla',
    10: 'no_mascarilla',
    11: 'pantalón',
    12: 'no_pantalón',
    13: 'botas',
    14: 'no_botas',
}

# Clases que indican ausencia de EPP → se marcan como violación
VIOLATION_CLASSES = {
    'no_guante', 'no_gafas', 'no_gorro',
    'no_bata', 'no_mascarilla', 'no_pantalón', 'no_botas',
}

# Colores BGR para OpenCV
PERSON_COLOR = (255, 0, 0)  # azul

EPP_COLORS = {
    1:  (0, 0, 200),      # guante       → rojo
    2:  (0, 100, 200),    # no_guante    → naranja-rojo
    3:  (0, 200, 0),      # gafas        → verde
    4:  (0, 150, 150),    # no_gafas     → oliva
    5:  (200, 0, 200),    # gorro        → magenta
    6:  (150, 0, 150),    # no_gorro     → púrpura
    7:  (200, 200, 0),    # bata         → cian
    8:  (100, 100, 0),    # no_bata      → cian oscuro
    9:  (200, 0, 100),    # mascarilla   → violeta
    10: (150, 0, 80),     # no_mascarilla→ violeta oscuro
    11: (0, 165, 255),    # pantalón     → naranja
    12: (0, 100, 200),    # no_pantalón  → naranja oscuro
    13: (128, 0, 128),    # botas        → morado
    14: (80, 0, 80),      # no_botas     → morado oscuro
}

# ---------------------------------------------------------------------------
# ORM (definiciones de tablas)
# ---------------------------------------------------------------------------
class ModelConfig(db.Model):
    __tablename__ = 'model_config'
    id             = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name           = db.Column(db.String(100), nullable=False, unique=True)
    weights_path   = db.Column(db.String(255))
    conf_threshold = db.Column(db.Float,   default=0.25)
    iou_threshold  = db.Column(db.Float,   default=0.45)
    img_size       = db.Column(db.Integer, default=640)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    metrics = db.relationship('TrainingMetric', backref='model', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id':             self.id,
            'name':           self.name,
            'weights_path':   self.weights_path,
            'conf_threshold': self.conf_threshold,
            'iou_threshold':  self.iou_threshold,
            'img_size':       self.img_size,
            'created_at':     self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at':     self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
        }

class Session(db.Model):
    __tablename__ = 'sessions'
    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp     = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    source        = db.Column(db.String(50))
    image_path    = db.Column(db.String(512))
    output_path   = db.Column(db.String(512))
    duration_ms   = db.Column(db.Integer)
    total_persons = db.Column(db.Integer, default=0)
    total_epp_ok  = db.Column(db.Integer, default=0)
    detections = db.relationship('Detection', backref='session', lazy=True, cascade='all, delete-orphan')
    alerts     = db.relationship('Alert', backref='session', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id':            self.id,
            'timestamp':     self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else None,
            'source':        self.source,
            'image_path':    self.image_path,
            'output_path':   self.output_path,
            'duration_ms':   self.duration_ms,
            'total_persons': self.total_persons,
            'total_epp_ok':  self.total_epp_ok,
        }

class Detection(db.Model):
    __tablename__ = 'detections'
    id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id   = db.Column(db.Integer, db.ForeignKey('sessions.id', ondelete='CASCADE'), index=True)
    model_used   = db.Column(db.String(100))
    class_name   = db.Column(db.String(50), index=True)
    confidence   = db.Column(db.Float)
    x1           = db.Column(db.Float)
    y1           = db.Column(db.Float)
    x2           = db.Column(db.Float)
    y2           = db.Column(db.Float)
    is_violation = db.Column(db.Boolean, default=False, index=True)
    person_id    = db.Column(db.Integer)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':           self.id,
            'session_id':   self.session_id,
            'model_used':   self.model_used,
            'class_name':   self.class_name,
            'confidence':   self.confidence,
            'x1': self.x1, 'y1': self.y1,
            'x2': self.x2, 'y2': self.y2,
            'is_violation': self.is_violation,
            'person_id':    self.person_id,
            'created_at':   self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }

class Alert(db.Model):
    __tablename__ = 'alerts'
    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id', ondelete='CASCADE'), index=True)
    alert_type = db.Column(db.String(50))
    severity   = db.Column(db.String(20))
    timestamp  = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    resolved   = db.Column(db.Boolean, default=False)
    notes      = db.Column(db.Text)

    def to_dict(self):
        return {
            'id':         self.id,
            'session_id': self.session_id,
            'alert_type': self.alert_type,
            'severity':   self.severity,
            'timestamp':  self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else None,
            'resolved':   self.resolved,
            'notes':      self.notes,
        }

class TrainingMetric(db.Model):
    __tablename__ = 'training_metrics'
    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    model_id   = db.Column(db.Integer, db.ForeignKey('model_config.id', ondelete='CASCADE'), index=True)
    epoch      = db.Column(db.Integer)
    box_loss   = db.Column(db.Float)
    cls_loss   = db.Column(db.Float)
    dfl_loss   = db.Column(db.Float)
    precision  = db.Column(db.Float)
    recall     = db.Column(db.Float)
    map50      = db.Column(db.Float)
    map50_95   = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':        self.id,
            'model_id':  self.model_id,
            'epoch':     self.epoch,
            'box_loss':  self.box_loss,
            'cls_loss':  self.cls_loss,
            'dfl_loss':  self.dfl_loss,
            'precision': self.precision,
            'recall':    self.recall,
            'map50':     self.map50,
            'map50_95':  self.map50_95,
        }


# ---------------------------------------------------------------------------
# Carga de modelos YOLO
# ---------------------------------------------------------------------------

model_person = None
model_epp    = None

def load_models():
    global model_person, model_epp
    try:
        from ultralytics import YOLO
        p = os.path.join(BASE_DIR, 'models', 'yolo26m.pt')
        e = os.path.join(BASE_DIR, 'models', 'modeloepp_v1.pt')
        if os.path.exists(p):
            model_person = YOLO(p)
            print(f'[OK] Personas: {p}')
        if os.path.exists(e):
            model_epp = YOLO(e)
            print(f'[OK] EPP: {e}')
    except Exception as ex:
        print(f'[WARN] Modelos no disponibles — modo demo. {ex}')

def run_inference(img_array):
    if model_epp is None or model_person is None:
        return []
    dets = []
    results_person = model_person(img_array, conf=0.25, classes=[0], imgsz=640, verbose=False, half=True)
    if results_person:
        for box in results_person[0].boxes:
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            dets.append({
                'class_name':  'persona',
                'confidence':  float(box.conf[0]),
                'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                'is_violation': False,
                'model_used':  'yolo26m',
                'class_id':    0,
            })
    results_epp = model_epp(img_array, conf=0.1, imgsz=640, verbose=False, half=True)
    if results_epp:
        for box in results_epp[0].boxes:
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            cls_id     = int(box.cls[0])
            class_name = EPP_NAMES.get(cls_id, f'class_{cls_id}')
            dets.append({
                'class_name':  class_name,
                'confidence':  float(box.conf[0]),
                'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                'is_violation': class_name in VIOLATION_CLASSES,
                'model_used':  'modeloepp_v1',
                'class_id':    cls_id,
            })
    return dets

def draw_boxes(img, dets):
    out = img.copy()
    for d in dets:
        x1, y1, x2, y2 = int(d['x1']), int(d['y1']), int(d['x2']), int(d['y2'])
        cls_id = d.get('class_id', 0)
        if d['class_name'] == 'persona':
            col = PERSON_COLOR
        else:
            col = EPP_COLORS.get(cls_id, (200, 200, 200))
        cv2.rectangle(out, (x1, y1), (x2, y2), col, 2)
        lbl = f"{d['class_name']} {d['confidence']:.2f}"
        (tw, th), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(out, (x1, y1 - th - 6), (x1 + tw + 6, y1), col, -1)
        cv2.putText(out, lbl, (x1 + 3, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return out


# ---------------------------------------------------------------------------
# Cámara robusta (stream MJPEG)
# ---------------------------------------------------------------------------

INDICES_CAMARA = [0, 1, 2, 3]
FORMATOS_CAM = ['MJPG', 'YUYV']
RESOLUCIONES_CAM = [(640, 480), (320, 240), (160, 120)]

camera = None
current_cam_config = None
camera_active = False   # el frontend controla este flag

def init_camera_robust():
    global camera, current_cam_config
    for idx in INDICES_CAMARA:
        for fourcc_str in FORMATOS_CAM:
            fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
            for width, height in RESOLUCIONES_CAM:
                print(f"Probando cámara {idx} con {fourcc_str} {width}x{height}...")
                cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
                if not cap.isOpened():
                    continue
                cap.set(cv2.CAP_PROP_FOURCC, fourcc)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                cap.set(cv2.CAP_PROP_FPS, 30)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                for _ in range(5):
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        print(f"✅ Cámara configurada: {idx} {fourcc_str} {width}x{height}")
                        camera = cap
                        current_cam_config = (idx, fourcc_str, width, height)
                        return True
                    time.sleep(0.1)
                cap.release()
    print("❌ No se pudo abrir ninguna cámara")
    return False

def get_camera():
    global camera
    if camera is None or not camera.isOpened():
        if init_camera_robust():
            return camera
        else:
            return None
    return camera

# ---------------------------------------------------------------------------
# Últimos datos para estadísticas y guardado
# ---------------------------------------------------------------------------

last_frame = None
last_stats = {
    'total_persons': 0,
    'violations':    0,
    'detections':    [],
    'fps':           0,
}
last_stats_lock = threading.Lock()

_fps_counter = 0
_fps_ts      = time.time()
_fps_current = 0

def update_last_stats(dets, persons, viols):
    global _fps_counter, _fps_ts, _fps_current
    _fps_counter += 1
    now     = time.time()
    elapsed = now - _fps_ts
    if elapsed >= 1.0:
        _fps_current = round(_fps_counter / elapsed, 1)
        _fps_counter = 0
        _fps_ts      = now
    with last_stats_lock:
        last_stats['total_persons'] = persons
        last_stats['violations']    = viols
        last_stats['detections']    = dets
        last_stats['fps']           = _fps_current

def generate_frames():
    global last_frame, camera, camera_active
    camera_active = True
    while camera_active:
        cap = get_camera()
        if cap is None:
            time.sleep(1)
            continue
        ret, frame = cap.read()
        if not ret:
            camera = None
            cap = get_camera()
            if cap is None:
                time.sleep(1)
                continue
            ret, frame = cap.read()
            if not ret:
                continue

        last_frame = frame.copy()

        detections      = run_inference(frame)
        frame_with_boxes = draw_boxes(frame, detections)

        persons = sum(1 for d in detections if d['class_name'] == 'persona')
        viols   = len([d for d in detections if d['is_violation']])
        update_last_stats(detections, persons, viols)

        ret, jpeg = cv2.imencode('.jpg', frame_with_boxes, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ret:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

    # liberar la cámara al salir del bucle → apaga el LED
    if camera is not None:
        camera.release()
        camera = None

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/stop_camera', methods=['POST'])
def stop_camera():
    global camera_active, camera
    camera_active = False
    # release inmediato por si el generador tarda en notar el flag
    if camera is not None:
        camera.release()
        camera = None
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Rutas HTML
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/database')
def database():
    return render_template('database.html')


# ---------------------------------------------------------------------------
# API — detección principal (para subir imagen)
# ---------------------------------------------------------------------------

@app.route('/api/detect', methods=['POST'])
def detect():
    t0 = time.time()
    if 'image' not in request.files:
        return jsonify({'error': 'No imagen recibida'}), 400
    img = cv2.imdecode(np.frombuffer(request.files['image'].read(), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({'error': 'Imagen inválida o corrupta'}), 400
    save_images = request.form.get('save_images', 'true').lower() != 'false'
    source      = request.form.get('source', 'upload')
    if model_epp is None and model_person is None:
        return jsonify({
            'warning':       'Modelos no cargados — coloca los .pt en models/',
            'models_loaded': False,
            'detections':    [],
            'total_persons': 0,
            'violations':    0,
            'duration_ms':   int((time.time() - t0) * 1000),
        }), 200
    dets    = run_inference(img)
    img_out = draw_boxes(img, dets)
    dur     = int((time.time() - t0) * 1000)
    persons = sum(1 for d in dets if d['class_name'] == 'persona')
    viols   = [d for d in dets if d['is_violation']]
    in_path_rel  = None
    out_path_rel = None
    if save_images:
        ts           = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        in_path      = os.path.join(UPLOAD_FOLDER, f'in_{ts}.jpg')
        out_path     = os.path.join(OUTPUT_FOLDER, f'out_{ts}.jpg')
        cv2.imwrite(in_path,  img)
        cv2.imwrite(out_path, img_out)
        in_path_rel  = f'static/uploads/in_{ts}.jpg'
        out_path_rel = f'static/outputs/out_{ts}.jpg'
    else:
        tmp_path = os.path.join(OUTPUT_FOLDER, '_tmp_preview.jpg')
        cv2.imwrite(tmp_path, img_out)
        out_path = tmp_path
    ses = Session(
        source        = source,
        image_path    = in_path_rel,
        output_path   = out_path_rel,
        duration_ms   = dur,
        total_persons = persons,
        total_epp_ok  = max(0, persons - len(viols)),
    )
    db.session.add(ses)
    db.session.flush()
    for d in dets:
        db.session.add(Detection(
            session_id   = ses.id,
            model_used   = d['model_used'],
            class_name   = d['class_name'],
            confidence   = d['confidence'],
            x1=d['x1'], y1=d['y1'], x2=d['x2'], y2=d['y2'],
            is_violation = d['is_violation'],
        ))
    for v in viols:
        db.session.add(Alert(session_id=ses.id, alert_type=v['class_name'], severity='danger'))
    db.session.commit()
    with open(out_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    if not save_images and os.path.exists(out_path):
        os.remove(out_path)
    return jsonify({
        'session_id':    ses.id,
        'detections':    dets,
        'duration_ms':   dur,
        'total_persons': persons,
        'violations':    len(viols),
        'saved_images':  save_images,
        'output_image':  f'data:image/jpeg;base64,{b64}',
    })


# ---------------------------------------------------------------------------
# CRUD — detections
# ---------------------------------------------------------------------------

@app.route('/api/detections', methods=['GET'])
def detections_read():
    pagina   = int(request.args.get('pagina', 1))
    limite   = min(int(request.args.get('limite', 20)), 200)
    clase    = request.args.get('clase', '')
    estado   = request.args.get('estado', '')
    modelo   = request.args.get('modelo', '')
    conf_min = float(request.args.get('conf_min', 0))
    q = Detection.query
    if clase:            q = q.filter(Detection.class_name == clase)
    if estado == 'viol': q = q.filter(Detection.is_violation == True)
    if estado == 'ok':   q = q.filter(Detection.is_violation == False)
    if modelo:           q = q.filter(Detection.model_used == modelo)
    if conf_min > 0:     q = q.filter(Detection.confidence >= conf_min)
    q = q.order_by(Detection.id.desc())
    total = q.count()
    rows  = q.offset((pagina - 1) * limite).limit(limite).all()
    return jsonify({'total': total, 'pagina': pagina, 'data': [r.to_dict() for r in rows]})

@app.route('/api/detections/<int:rid>', methods=['GET'])
def detection_get(rid):
    return jsonify(Detection.query.get_or_404(rid).to_dict())

@app.route('/api/detections', methods=['POST'])
def detection_create():
    d = request.get_json()
    try:
        rec = Detection(
            session_id   = d.get('session_id'),
            model_used   = d.get('model_used'),
            class_name   = d.get('class_name'),
            confidence   = d.get('confidence'),
            x1=d.get('x1', 0), y1=d.get('y1', 0),
            x2=d.get('x2', 0), y2=d.get('y2', 0),
            is_violation = bool(d.get('is_violation', False)),
            person_id    = d.get('person_id'),
        )
        db.session.add(rec)
        db.session.commit()
        return jsonify({'ok': True, 'id': rec.id, 'data': rec.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/detections/<int:rid>', methods=['PUT'])
def detection_update(rid):
    rec = Detection.query.get_or_404(rid)
    d   = request.get_json()
    try:
        for field in ['model_used', 'class_name', 'confidence', 'x1', 'y1', 'x2', 'y2', 'is_violation', 'person_id']:
            if field in d:
                setattr(rec, field, d[field])
        db.session.commit()
        return jsonify({'ok': True, 'data': rec.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/detections/<int:rid>', methods=['DELETE'])
def detection_delete(rid):
    rec = Detection.query.get_or_404(rid)
    try:
        db.session.delete(rec)
        db.session.commit()
        return jsonify({'ok': True, 'deleted_id': rid})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# CRUD — sessions
# ---------------------------------------------------------------------------

@app.route('/api/sessions', methods=['GET'])
def sessions_read():
    pagina = int(request.args.get('pagina', 1))
    limite = min(int(request.args.get('limite', 20)), 200)
    source = request.args.get('source', '')
    q = Session.query
    if source: q = q.filter(Session.source == source)
    q = q.order_by(Session.timestamp.desc())
    total = q.count()
    rows  = q.offset((pagina - 1) * limite).limit(limite).all()
    return jsonify({'total': total, 'pagina': pagina, 'data': [r.to_dict() for r in rows]})


@app.route('/api/sessions/<int:rid>', methods=['GET'])
def session_get(rid):
    row  = Session.query.get_or_404(rid)
    data = row.to_dict()
    data['detections'] = [d.to_dict() for d in row.detections]
    data['alerts']     = [a.to_dict() for a in row.alerts]
    return jsonify(data)


@app.route('/api/sessions', methods=['POST'])
def session_create():
    d = request.get_json()
    try:
        rec = Session(
            source        = d.get('source'),
            image_path    = d.get('image_path', ''),
            output_path   = d.get('output_path', ''),
            duration_ms   = d.get('duration_ms'),
            total_persons = d.get('total_persons', 0),
            total_epp_ok  = d.get('total_epp_ok', 0),
        )
        db.session.add(rec)
        db.session.commit()
        return jsonify({'ok': True, 'id': rec.id, 'data': rec.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/sessions/<int:rid>', methods=['PUT'])
def session_update(rid):
    rec = Session.query.get_or_404(rid)
    d   = request.get_json()
    try:
        for field in ['source', 'image_path', 'output_path', 'duration_ms', 'total_persons', 'total_epp_ok']:
            if field in d: setattr(rec, field, d[field])
        db.session.commit()
        return jsonify({'ok': True, 'data': rec.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/sessions/<int:rid>', methods=['DELETE'])
def session_delete(rid):
    rec = Session.query.get_or_404(rid)
    try:
        db.session.delete(rec)
        db.session.commit()
        return jsonify({'ok': True, 'deleted_id': rid})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# CRUD — alerts
# ---------------------------------------------------------------------------

@app.route('/api/alerts', methods=['GET'])
def alerts_read():
    pagina   = int(request.args.get('pagina', 1))
    limite   = min(int(request.args.get('limite', 20)), 200)
    resolved = request.args.get('resolved', '')
    severity = request.args.get('severity', '')
    q = Alert.query
    if resolved == 'true':  q = q.filter(Alert.resolved == True)
    if resolved == 'false': q = q.filter(Alert.resolved == False)
    if severity: q = q.filter(Alert.severity == severity)
    q = q.order_by(Alert.timestamp.desc())
    total = q.count()
    rows  = q.offset((pagina - 1) * limite).limit(limite).all()
    return jsonify({'total': total, 'pagina': pagina, 'data': [r.to_dict() for r in rows]})


@app.route('/api/alerts/<int:rid>', methods=['GET'])
def alert_get(rid):
    return jsonify(Alert.query.get_or_404(rid).to_dict())


@app.route('/api/alerts', methods=['POST'])
def alert_create():
    d = request.get_json()
    try:
        rec = Alert(
            session_id = d.get('session_id'),
            alert_type = d.get('alert_type'),
            severity   = d.get('severity', 'warn'),
            resolved   = bool(d.get('resolved', False)),
            notes      = d.get('notes', ''),
        )
        db.session.add(rec)
        db.session.commit()
        return jsonify({'ok': True, 'id': rec.id, 'data': rec.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts/<int:rid>', methods=['PUT'])
def alert_update(rid):
    rec = Alert.query.get_or_404(rid)
    d   = request.get_json()
    try:
        for field in ['alert_type', 'severity', 'resolved', 'notes']:
            if field in d: setattr(rec, field, d[field])
        db.session.commit()
        return jsonify({'ok': True, 'data': rec.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts/<int:rid>', methods=['DELETE'])
def alert_delete(rid):
    rec = Alert.query.get_or_404(rid)
    try:
        db.session.delete(rec)
        db.session.commit()
        return jsonify({'ok': True, 'deleted_id': rid})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# CRUD — training_metrics
# ---------------------------------------------------------------------------

@app.route('/api/metrics', methods=['GET'])
def metrics_read():
    model_id = request.args.get('model_id', type=int)
    q = TrainingMetric.query
    if model_id: q = q.filter(TrainingMetric.model_id == model_id)
    q = q.order_by(TrainingMetric.epoch)
    rows = q.all()
    return jsonify({'total': len(rows), 'data': [r.to_dict() for r in rows]})


@app.route('/api/metrics/<int:rid>', methods=['GET'])
def metric_get(rid):
    return jsonify(TrainingMetric.query.get_or_404(rid).to_dict())


@app.route('/api/metrics', methods=['POST'])
def metric_create():
    d = request.get_json()
    try:
        rec = TrainingMetric(
            model_id  = d.get('model_id', 1),
            epoch     = d.get('epoch'),
            box_loss  = d.get('box_loss'),
            cls_loss  = d.get('cls_loss'),
            dfl_loss  = d.get('dfl_loss'),
            precision = d.get('precision'),
            recall    = d.get('recall'),
            map50     = d.get('map50'),
            map50_95  = d.get('map50_95'),
        )
        db.session.add(rec)
        db.session.commit()
        return jsonify({'ok': True, 'id': rec.id, 'data': rec.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics/<int:rid>', methods=['PUT'])
def metric_update(rid):
    rec = TrainingMetric.query.get_or_404(rid)
    d   = request.get_json()
    try:
        for field in ['epoch', 'box_loss', 'cls_loss', 'dfl_loss', 'precision', 'recall', 'map50', 'map50_95']:
            if field in d: setattr(rec, field, d[field])
        db.session.commit()
        return jsonify({'ok': True, 'data': rec.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics/<int:rid>', methods=['DELETE'])
def metric_delete(rid):
    rec = TrainingMetric.query.get_or_404(rid)
    try:
        db.session.delete(rec)
        db.session.commit()
        return jsonify({'ok': True, 'deleted_id': rid})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# CRUD — model_config
# ---------------------------------------------------------------------------

@app.route('/api/models', methods=['GET'])
def models_read():
    rows = ModelConfig.query.all()
    return jsonify({'total': len(rows), 'data': [r.to_dict() for r in rows]})


@app.route('/api/models/<int:rid>', methods=['GET'])
def model_get(rid):
    return jsonify(ModelConfig.query.get_or_404(rid).to_dict())


@app.route('/api/models', methods=['POST'])
def model_create():
    d = request.get_json()
    try:
        rec = ModelConfig(
            name           = d.get('name'),
            weights_path   = d.get('weights_path', ''),
            conf_threshold = d.get('conf_threshold', 0.25),
            iou_threshold  = d.get('iou_threshold',  0.45),
            img_size       = d.get('img_size', 640),
        )
        db.session.add(rec)
        db.session.commit()
        return jsonify({'ok': True, 'id': rec.id, 'data': rec.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/models/<int:rid>', methods=['PUT'])
def model_update(rid):
    rec = ModelConfig.query.get_or_404(rid)
    d   = request.get_json()
    try:
        for field in ['name', 'weights_path', 'conf_threshold', 'iou_threshold', 'img_size']:
            if field in d: setattr(rec, field, d[field])
        rec.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'ok': True, 'data': rec.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/models/<int:rid>', methods=['DELETE'])
def model_delete(rid):
    rec = ModelConfig.query.get_or_404(rid)
    try:
        db.session.delete(rec)
        db.session.commit()
        return jsonify({'ok': True, 'deleted_id': rid})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Stats y rutas de compatibilidad
# ---------------------------------------------------------------------------

@app.route('/api/stats', methods=['GET'])
def stats():
    avg_conf = db.session.query(db.func.avg(Detection.confidence)).scalar() or 0
    return jsonify({
        'total_detections':  Detection.query.count(),
        'total_sessions':    Session.query.count(),
        'total_violations':  Detection.query.filter_by(is_violation=True).count(),
        'total_alerts':      Alert.query.count(),
        'unresolved_alerts': Alert.query.filter_by(resolved=False).count(),
        'avg_confidence':    round(float(avg_conf), 4),
    })

@app.route('/api/historial')
def historial_compat():
    tabla = request.args.get('tabla', 'detections')
    REDIRECT = {
        'sessions': '/api/sessions', 'alerts': '/api/alerts',
        'training_metrics': '/api/metrics', 'model_config': '/api/models',
    }
    if tabla in REDIRECT:
        args = request.query_string.decode()
        return redirect(f"{REDIRECT[tabla]}?{args}")
    return detections_read()

@app.route('/api/metricas')
def metricas_compat():
    model_id = request.args.get('model_id', 1, type=int)
    rows = TrainingMetric.query.filter_by(model_id=model_id).order_by(TrainingMetric.epoch).all()
    if not rows:
        return jsonify({'epocas': [], 'map50': [], 'box_loss': [], 'cls_loss': [],
                        'dfl_loss': [], 'precision': [], 'recall': []})
    return jsonify({
        'epocas':    [r.epoch     for r in rows],
        'map50':     [r.map50     for r in rows],
        'box_loss':  [r.box_loss  for r in rows],
        'cls_loss':  [r.cls_loss  for r in rows],
        'dfl_loss':  [r.dfl_loss  for r in rows],
        'precision': [r.precision for r in rows],
        'recall':    [r.recall    for r in rows],
    })

@app.route('/api/config', methods=['GET'])
def config_compat():
    return models_read()

@app.route('/api/config/<int:cid>', methods=['PUT'])
def config_update_compat(cid):
    return model_update(cid)


# ---------------------------------------------------------------------------
# Últimos datos para estadísticas y guardado (endpoints adicionales)
# ---------------------------------------------------------------------------

@app.route('/api/latest_stats')
def latest_stats():
    with last_stats_lock:
        return jsonify(last_stats)

@app.route('/api/save_current', methods=['POST'])
def save_current():
    """Guarda el último frame procesado en la base de datos."""
    global last_frame
    if last_frame is None:
        return jsonify({'error': 'No hay frame disponible'}), 400

    save_images = request.json.get('save_images', True) if request.is_json else True
    source = request.json.get('source', 'camara') if request.is_json else 'camara'

    # Copiar el frame para no interferir con el stream
    frame_to_save = last_frame.copy()

    # Inferencia (reutiliza run_inference)
    dets = run_inference(frame_to_save)
    img_out = draw_boxes(frame_to_save, dets)
    persons = sum(1 for d in dets if d['class_name'] == 'persona')
    viols = [d for d in dets if d['is_violation']]

    in_path_rel = None
    out_path_rel = None

    if save_images:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        in_path = os.path.join(UPLOAD_FOLDER, f'in_{ts}.jpg')
        out_path = os.path.join(OUTPUT_FOLDER, f'out_{ts}.jpg')
        cv2.imwrite(in_path, frame_to_save)
        cv2.imwrite(out_path, img_out)
        in_path_rel = f'static/uploads/in_{ts}.jpg'
        out_path_rel = f'static/outputs/out_{ts}.jpg'

    ses = Session(
        source=source,
        image_path=in_path_rel,
        output_path=out_path_rel,
        duration_ms=0,
        total_persons=persons,
        total_epp_ok=max(0, persons - len(viols)),
    )
    db.session.add(ses)
    db.session.flush()

    for d in dets:
        db.session.add(Detection(
            session_id=ses.id,
            model_used=d['model_used'],
            class_name=d['class_name'],
            confidence=d['confidence'],
            x1=d['x1'], y1=d['y1'], x2=d['x2'], y2=d['y2'],
            is_violation=d['is_violation'],
        ))
    for v in viols:
        db.session.add(Alert(session_id=ses.id, alert_type=v['class_name'], severity='danger'))

    db.session.commit()
    return jsonify({'session_id': ses.id, 'saved': True})


# ---------------------------------------------------------------------------
# Datos iniciales
# ---------------------------------------------------------------------------

def seed_db():
    if ModelConfig.query.count() == 0:
        db.session.add_all([
            ModelConfig(name='yolo26m',      weights_path='models/yolo26m.pt',      conf_threshold=0.25, iou_threshold=0.45, img_size=640),
            ModelConfig(name='modeloepp_v1', weights_path='models/modeloepp_v1.pt', conf_threshold=0.35, iou_threshold=0.45, img_size=640),
        ])
        db.session.flush()
    if TrainingMetric.query.count() == 0:
        epp_model = ModelConfig.query.filter_by(name='modeloepp_v1').first()
        if epp_model:
            datos = [
                (1, 1.863, 3.429, 1.480, 0.035, 0.166, 0.0003),
                (2, 1.558, 2.011, 1.214, 0.292, 0.311, 0.0006),
                (3, 1.490, 1.791, 1.219, 0.349, 0.175, 0.0009),
                (4, 1.424, 1.579, 1.190, 0.362, 0.182, 0.0009),
                (5, 1.423, 1.463, 1.176, 0.449, 0.259, 0.0008),
                (6, 1.366, 1.382, 1.154, 0.427, 0.454, 0.0008),
            ]
            for ep, bl, cl, dl, pr, rc, mp in datos:
                db.session.add(TrainingMetric(
                    model_id=epp_model.id, epoch=ep,
                    box_loss=bl, cls_loss=cl, dfl_loss=dl,
                    precision=pr, recall=rc, map50=mp,
                ))
    db.session.commit()
    print('[OK] Base de datos inicializada')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_db()
    load_models()
    app.run(debug=True, host='0.0.0.0', port=5000)