import os, sqlite3, secrets, uuid, json
from datetime import datetime, timezone
from pathlib import Path
from functools import wraps
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "smartfarm.db"
UPLOAD_DIR = BASE / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED = {"jpg", "jpeg", "png", "webp"}
MAX_UPLOAD = 8 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET", secrets.token_hex(32))
ROBOT_API_KEY = os.getenv("ROBOT_API_KEY", "CHANGE_THIS_ROBOT_KEY")

# FAO Irrigation and Drainage Paper 29, Annex 1.
# Threshold (a) and slope (b) are for ECe: saturated-paste extract, dS/m at 25 C.
CROP_SALINITY = [
    {"crop":"Barley","crop_ar":"الشعير","threshold":8.0,"slope":5.0},
    {"crop":"Cotton","crop_ar":"القطن","threshold":7.7,"slope":5.2},
    {"crop":"Wheat","crop_ar":"القمح","threshold":6.0,"slope":7.1},
    {"crop":"Sorghum","crop_ar":"الذرة الرفيعة","threshold":6.8,"slope":16.0},
    {"crop":"Soybean","crop_ar":"فول الصويا","threshold":5.0,"slope":20.0},
    {"crop":"Cowpea","crop_ar":"اللوبيا","threshold":4.9,"slope":12.0},
    {"crop":"Sunflower","crop_ar":"عباد الشمس","threshold":4.8,"slope":5.0},
    {"crop":"Peanut","crop_ar":"الفول السوداني","threshold":3.2,"slope":29.0},
    {"crop":"Rice (paddy)","crop_ar":"الأرز","threshold":3.0,"slope":12.0},
    {"crop":"Cucumber","crop_ar":"الخيار","threshold":2.5,"slope":13.0},
    {"crop":"Maize","crop_ar":"الذرة الشامية","threshold":1.7,"slope":12.0},
    {"crop":"Broad bean","crop_ar":"الفول البلدي","threshold":1.6,"slope":9.6},
    {"crop":"Lettuce","crop_ar":"الخس","threshold":1.3,"slope":13.0},
    {"crop":"Onion","crop_ar":"البصل","threshold":1.2,"slope":16.0},
    {"crop":"Carrot","crop_ar":"الجزر","threshold":1.0,"slope":14.0},
    {"crop":"Common bean","crop_ar":"الفاصوليا","threshold":1.0,"slope":19.0},
    {"crop":"Muskmelon","crop_ar":"الكنتالوب","threshold":1.0,"slope":8.4},
]

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS readings (
          id INTEGER PRIMARY KEY AUTOINCREMENT, robot_id TEXT NOT NULL,
          zone_id TEXT NOT NULL, moisture REAL, soil_temp REAL, ph REAL, ec REAL,
          battery REAL, ec_method TEXT, ec_unit TEXT, sensor_model TEXT,
          calibration_date TEXT, measurement_depth_cm REAL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_readings_zone_time ON readings(zone_id, created_at);
        CREATE TABLE IF NOT EXISTS plant_images (
          id INTEGER PRIMARY KEY AUTOINCREMENT, zone_id TEXT NOT NULL, crop TEXT,
          filename TEXT NOT NULL, notes TEXT, status TEXT NOT NULL DEFAULT 'uploaded',
          diagnosis_json TEXT, created_at TEXT NOT NULL
        );
        """)
        # Migrate databases made by the first Smart Farm ZIP.
        rcols = {r[1] for r in con.execute("PRAGMA table_info(readings)")}
        for name, typ in (("ec_method","TEXT"),("ec_unit","TEXT"),("sensor_model","TEXT"),
                          ("calibration_date","TEXT"),("measurement_depth_cm","REAL")):
            if name not in rcols:
                con.execute(f"ALTER TABLE readings ADD COLUMN {name} {typ}")
        icols = {r[1] for r in con.execute("PRAGMA table_info(plant_images)")}
        if "diagnosis_json" not in icols:
            con.execute("ALTER TABLE plant_images ADD COLUMN diagnosis_json TEXT")

def robot_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        supplied = request.headers.get("X-API-Key", "")
        if ROBOT_API_KEY == "CHANGE_THIS_ROBOT_KEY" or not secrets.compare_digest(supplied, ROBOT_API_KEY):
            return jsonify({"ok":False,"error":"Unauthorized: configure ROBOT_API_KEY and send X-API-Key."}), 401
        return fn(*args, **kwargs)
    return wrapper

def valid_zone(zone):
    try:
        zone = str(zone).upper()
        row = int(zone[1:]); col = ord(zone[0])-64
        return len(zone) <= 4 and 1 <= row <= 16 and 1 <= col <= 16
    except Exception:
        return False

def latest_readings():
    with db() as con:
        rows = con.execute("""SELECT r.* FROM readings r JOIN
          (SELECT zone_id, MAX(id) max_id FROM readings GROUP BY zone_id) x
          ON r.id=x.max_id""").fetchall()
    return {r["zone_id"]:dict(r) for r in rows}

def recommendation(reading):
    if not reading:
        return {"status":"no_data","label":"No data","label_ar":"لا توجد بيانات",
                "detail":"No sensor reading received yet.","detail_ar":"لم يتم استلام قراءة حساسات بعد.","crops":[]}
    ec, method, unit = reading.get("ec"), (reading.get("ec_method") or "").lower(), (reading.get("ec_unit") or "").lower().replace(" ","")
    if ec is None:
        status, en, ar = "insufficient","EC is missing; no salinity crop screening is possible.","قراءة EC غير موجودة؛ لا يمكن إجراء فحص ملوحة للمحاصيل."
        crops=[]
    elif method not in {"ece","saturation_extract","saturated_paste_extract"} or unit not in {"ds/m","ds/m@25c","ds/m25c"}:
        status="method_mismatch"
        en="FAO thresholds require ECe from a saturated-paste extract at 25°C in dS/m. This reading is not verified as ECe, so crop ranking is withheld."
        ar="حدود FAO تتطلب ECe من مستخلص العجينة المشبعة عند 25°م بوحدة dS/m. هذه القراءة غير مؤكدة كـ ECe، لذلك لن نرتب المحاصيل."
        crops=[]
    else:
        status="screening"
        en="Relative-yield screening uses FAO ECe threshold/slope values. It is not a yield forecast and does not include cultivar, climate, irrigation, soil texture, drainage or local management."
        ar="الفحص النسبي يستخدم حدود ومعاملات FAO لقيمة ECe. ليس توقعًا للإنتاج ولا يشمل الصنف أو المناخ أو الري أو قوام التربة أو الصرف أو الإدارة المحلية."
        crops=[]
        for c in CROP_SALINITY:
            yr=max(0.0,min(100.0,100.0-c["slope"]*max(0.0,ec-c["threshold"])))
            crops.append({**c,"estimated_relative_yield_pct":round(yr,1)})
        crops.sort(key=lambda x:x["estimated_relative_yield_pct"],reverse=True)
    return {"status":status,"label":"Salinity screening only","label_ar":"فحص الملوحة فقط",
            "detail":en,"detail_ar":ar,"crops":crops,
            "source":"FAO Irrigation and Drainage Paper 29, Annex 1"}

def run_plant_ai(image_path, crop_hint=""):
    """Lazy-loads a real Hugging Face image classifier locally on the server."""
    try:
        from PIL import Image
        import torch
        from transformers import AutoImageProcessor, AutoModelForImageClassification
        model_id=os.getenv("PLANT_MODEL_ID","rodynaemad/plant-disease-dinov2-small")
        if not hasattr(run_plant_ai,"_model"):
            run_plant_ai._processor=AutoImageProcessor.from_pretrained(model_id)
            run_plant_ai._model=AutoModelForImageClassification.from_pretrained(model_id)
            run_plant_ai._model.eval()
        image=Image.open(image_path).convert("RGB")
        inputs=run_plant_ai._processor(images=image,return_tensors="pt")
        with torch.no_grad():
            logits=run_plant_ai._model(**inputs).logits
            probs=torch.softmax(logits,dim=-1)[0]
        scores,ids=torch.topk(probs,k=min(3,probs.shape[0]))
        preds=[]
        for score,idx in zip(scores.tolist(),ids.tolist()):
            label=run_plant_ai._model.config.id2label.get(idx,str(idx))
            parts=label.split("___",1)
            preds.append({"label":label,"crop":parts[0].replace("_"," "),
                          "condition":parts[1].replace("_"," ") if len(parts)>1 else label,
                          "confidence":round(float(score),4)})
        top=preds[0]
        hint=(crop_hint or "").strip().lower()
        mismatch=bool(hint and hint not in top["crop"].lower() and top["crop"].lower() not in hint)
        threshold=float(os.getenv("PLANT_AI_CONFIDENCE_THRESHOLD","0.65"))
        uncertain=top["confidence"] < threshold or mismatch
        msg=("Uncertain: confidence is low or the crop does not match. Retake the photo or seek expert review."
             if uncertain else
             "AI screening candidate only. This 38-class model was evaluated mainly on controlled leaf images; confirm with an agronomist before any treatment.")
        return {"available":True,"model":model_id,"status":"uncertain" if uncertain else "screening_result",
                "message":msg,"top_predictions":preds,"threshold":threshold,
                "scope":"38 PlantVillage crop-condition classes; one clear leaf photo; not a confirmed field diagnosis."}
    except Exception as exc:
        return {"available":False,"status":"model_unavailable",
                "message":"AI model did not run. Install requirements-ai.txt and allow the server to download model weights.",
                "error":str(exc)[:250]}

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify({"ok":True,"service":"Smart Farm API"})

@app.get("/api/dashboard")
def dashboard():
    latest=latest_readings()
    with db() as con:
        total=con.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        images=con.execute("SELECT COUNT(*) FROM plant_images").fetchone()[0]
    return jsonify({"ok":True,"zones_total":256,"zones_with_data":len(latest),
                    "readings_total":total,"plant_images_total":images,
                    "latest":latest,"server_time":datetime.now(timezone.utc).isoformat()})

@app.get("/api/zones")
def zones():
    latest=latest_readings(); output=[]
    for row in range(1,17):
        for col in range(1,17):
            zone=f"{chr(64+col)}{row}"; r=latest.get(zone)
            output.append({"zone_id":zone,"reading":r,"recommendation":recommendation(r)})
    return jsonify({"ok":True,"zones":output})

@app.get("/api/readings")
def readings():
    zone=request.args.get("zone")
    with db() as con:
        rows=(con.execute("SELECT * FROM readings WHERE zone_id=? ORDER BY id DESC LIMIT 100",(zone.upper(),)).fetchall()
              if zone and valid_zone(zone) else
              con.execute("SELECT * FROM readings ORDER BY id DESC LIMIT 100").fetchall())
    return jsonify({"ok":True,"readings":[dict(r) for r in rows]})

@app.get("/api/crop-salinity")
def crop_salinity():
    return jsonify({"ok":True,"basis":"ECe dS/m at 25 C; saturated-paste extract",
                    "source":"FAO Irrigation and Drainage Paper 29, Annex 1","crops":CROP_SALINITY})

@app.post("/api/robot/readings")
@robot_auth
def receive_reading():
    data=request.get_json(silent=True) or {}
    zone=str(data.get("zone_id","")).upper()
    if not valid_zone(zone):
        return jsonify({"ok":False,"error":"zone_id must be A1 through P16"}),400
    values={}
    for field in ("moisture","soil_temp","ph","ec","battery"):
        value=data.get(field)
        if value in (None,""): values[field]=None
        else:
            try: values[field]=float(value)
            except (TypeError,ValueError): return jsonify({"ok":False,"error":f"{field} must be numeric or null"}),400
    limits = {"moisture":(0,100),"ph":(0,14),"battery":(0,100),"ec":(0,None),"soil_temp":(-20,80)}
    for field,(low,high) in limits.items():
        v=values[field]
        if v is not None and (v < low or (high is not None and v > high)):
            return jsonify({"ok":False,"error":f"{field} is outside the accepted input range {low} to {high if high is not None else '∞'}; verify units and sensor calibration."}),400
    depth=data.get("measurement_depth_cm")
    if depth not in (None,""):
        try: depth=float(depth)
        except (TypeError,ValueError): return jsonify({"ok":False,"error":"measurement_depth_cm must be numeric or null"}),400
        if not 0 < depth <= 200: return jsonify({"ok":False,"error":"measurement_depth_cm must be between 0 and 200 cm"}),400
    timestamp=datetime.now(timezone.utc).isoformat()
    with db() as con:
        cur=con.execute("""INSERT INTO readings
          (robot_id,zone_id,moisture,soil_temp,ph,ec,battery,ec_method,ec_unit,
           sensor_model,calibration_date,measurement_depth_cm,created_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (str(data.get("robot_id","smartfarm-01"))[:60],zone,values["moisture"],values["soil_temp"],
           values["ph"],values["ec"],values["battery"],str(data.get("ec_method",""))[:40],
           str(data.get("ec_unit",""))[:20],str(data.get("sensor_model",""))[:100],
           str(data.get("calibration_date",""))[:20],depth,timestamp))
        rid=cur.lastrowid
    return jsonify({"ok":True,"reading_id":rid,"zone_id":zone,"created_at":timestamp}),201

@app.post("/api/plant-images")
def upload_plant_image():
    file=request.files.get("image"); zone=str(request.form.get("zone_id","")).upper()
    if not valid_zone(zone): return jsonify({"ok":False,"error":"Choose a valid zone such as A1."}),400
    if not file or not file.filename: return jsonify({"ok":False,"error":"Choose an image."}),400
    ext=file.filename.rsplit(".",1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED: return jsonify({"ok":False,"error":"Use JPG, PNG or WEBP."}),400
    stored=f"{uuid.uuid4().hex}.{ext}"; path=UPLOAD_DIR/stored; file.save(path)
    if path.stat().st_size>MAX_UPLOAD:
        path.unlink(missing_ok=True); return jsonify({"ok":False,"error":"Image exceeds 8 MB."}),413
    crop=str(request.form.get("crop",""))[:80]; notes=str(request.form.get("notes",""))[:500]
    timestamp=datetime.now(timezone.utc).isoformat()
    with db() as con:
        cur=con.execute("""INSERT INTO plant_images(zone_id,crop,filename,notes,status,created_at)
          VALUES(?,?,?,?,?,?)""",(zone,crop,stored,notes,"processing",timestamp))
        image_id=cur.lastrowid
    diagnosis=run_plant_ai(path,crop)
    with db() as con:
        con.execute("UPDATE plant_images SET status=?,diagnosis_json=? WHERE id=?",
                    (diagnosis.get("status","model_unavailable"),json.dumps(diagnosis,ensure_ascii=False),image_id))
    return jsonify({"ok":True,"image_id":image_id,"status":diagnosis.get("status"),
                    "diagnosis":diagnosis,"image_url":f"/uploads/{stored}"}),201

@app.get("/api/plant-images")
def list_images():
    with db() as con:
        rows=con.execute("SELECT * FROM plant_images ORDER BY id DESC LIMIT 50").fetchall()
    result=[]
    for r in rows:
        item=dict(r)
        item["diagnosis"]=json.loads(item.pop("diagnosis_json") or "{}")
        result.append(item)
    return jsonify({"ok":True,"images":result})

@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR,filename)

@app.errorhandler(413)
def too_large(_):
    return jsonify({"ok":False,"error":"Maximum image size is 8 MB."}),413

init_db()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")),debug=os.getenv("FLASK_DEBUG")=="1")
