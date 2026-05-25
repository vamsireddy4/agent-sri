# face_auth.py
"""Local face enrollment + recognition (LBPH) for identity verification.

Ported and generalised from the original JARVIS face-login feature. Instead of
a single hard-coded user, this supports enrolling any number of people by name,
then verifying who is currently in front of the webcam.

Actions (parameter "action"):
  enroll  — register a face under a given "name" (captures samples + trains)
  verify  — recognise who is at the camera (a.k.a. "login")
  list    — list enrolled names
  remove  — delete an enrolled person by "name"

Needs cv2.face (opencv-contrib-python). The Haar cascade ships with OpenCV.
Model + samples are stored under face_data/ next to the app.
"""
import json
import sys
import time
from pathlib import Path

try:
    import cv2
    import numpy as np
    _CV2 = True
    _HAS_FACE = hasattr(cv2, "face")
except ImportError:
    _CV2 = False
    _HAS_FACE = False

# Lower LBPH confidence == better match (0 is a perfect match).
_MATCH_THRESHOLD = 70.0
_DEFAULT_SAMPLES = 30


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _data_dir() -> Path:
    d = _base_dir() / "face_data"
    (d / "samples").mkdir(parents=True, exist_ok=True)
    return d


def _model_path() -> Path:
    return _data_dir() / "trainer.yml"


def _labels_path() -> Path:
    return _data_dir() / "labels.json"


def _load_labels() -> dict:
    p = _labels_path()
    if p.exists():
        try:
            return {int(k): v for k, v in json.loads(p.read_text()).items()}
        except Exception:
            return {}
    return {}


def _save_labels(labels: dict) -> None:
    _labels_path().write_text(
        json.dumps({str(k): v for k, v in labels.items()}, indent=2)
    )


def _detector():
    cascade = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    return cv2.CascadeClassifier(str(cascade))


def _capture_face_crops(num_samples: int, timeout_s: float = 20.0):
    """Open the webcam and collect up to num_samples grayscale face crops."""
    detector = _detector()
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        return None, "Could not access the webcam."

    crops = []
    deadline = time.time() + timeout_s
    try:
        while len(crops) < num_samples and time.time() < deadline:
            ok, frame = cam.read()
            if not ok or frame is None:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(gray, scaleFactor=1.2,
                                              minNeighbors=5, minSize=(80, 80))
            for (x, y, w, h) in faces:
                crops.append(cv2.resize(gray[y:y + h, x:x + w], (200, 200)))
                break  # one face per frame
            time.sleep(0.05)
    finally:
        cam.release()
    return crops, None


def _retrain() -> int:
    """Rebuild the LBPH model from every stored sample. Returns sample count."""
    samples_root = _data_dir() / "samples"
    faces, labels = [], []
    for person_dir in samples_root.iterdir():
        if not person_dir.is_dir():
            continue
        try:
            pid = int(person_dir.name)
        except ValueError:
            continue
        for img_file in person_dir.glob("*.png"):
            img = cv2.imread(str(img_file), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                faces.append(img)
                labels.append(pid)

    if not faces:
        return 0
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(faces, np.array(labels))
    recognizer.write(str(_model_path()))
    return len(faces)


def _enroll(name: str, num_samples: int) -> str:
    labels = _load_labels()
    # Reuse an existing id if the name is already enrolled, else allocate one.
    existing = {v.lower(): k for k, v in labels.items()}
    pid = existing.get(name.lower(), (max(labels) + 1) if labels else 1)

    crops, err = _capture_face_crops(num_samples)
    if err:
        return err
    if not crops:
        return ("No face detected. Make sure your face is well-lit and "
                "centred in the camera, then try again.")

    person_dir = _data_dir() / "samples" / str(pid)
    person_dir.mkdir(parents=True, exist_ok=True)
    start = len(list(person_dir.glob("*.png")))
    for i, crop in enumerate(crops):
        cv2.imwrite(str(person_dir / f"{start + i}.png"), crop)

    labels[pid] = name
    _save_labels(labels)
    total = _retrain()
    return (f"Enrolled {name} with {len(crops)} new samples "
            f"({total} total across {len(labels)} people). "
            f"You can now verify your face.")


def _verify(threshold: float) -> str:
    if not _model_path().exists():
        return "No faces are enrolled yet. Enroll a face first."
    labels = _load_labels()
    if not labels:
        return "No faces are enrolled yet. Enroll a face first."

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(str(_model_path()))
    detector = _detector()

    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        return "Could not access the webcam."

    votes: dict[int, list] = {}
    deadline = time.time() + 8.0
    try:
        while time.time() < deadline and sum(len(v) for v in votes.values()) < 12:
            ok, frame = cam.read()
            if not ok or frame is None:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(gray, scaleFactor=1.2,
                                              minNeighbors=5, minSize=(80, 80))
            for (x, y, w, h) in faces:
                crop = cv2.resize(gray[y:y + h, x:x + w], (200, 200))
                pid, conf = recognizer.predict(crop)
                votes.setdefault(pid, []).append(conf)
                break
            time.sleep(0.05)
    finally:
        cam.release()

    if not votes:
        return "I couldn't detect a face at the camera."

    # Pick the most-voted id, judged by its best (lowest) confidence.
    best_pid = min(votes, key=lambda k: min(votes[k]))
    best_conf = min(votes[best_pid])
    if best_conf <= threshold:
        name = labels.get(best_pid, "unknown")
        return (f"Face recognised: {name} "
                f"(confidence {100 - best_conf:.0f}%). Welcome.")
    return "Face not recognised — you don't match any enrolled user."


def face_auth(parameters: dict, response=None, player=None,
              session_memory=None) -> str:
    if not _CV2:
        return "OpenCV is not installed — face features are unavailable."
    if not _HAS_FACE:
        return ("cv2.face is missing. Install it with "
                "'pip install opencv-contrib-python'.")

    params = parameters or {}
    action = str(params.get("action", "verify")).lower().strip()
    name = str(params.get("name", "")).strip()
    try:
        samples = int(params.get("samples", _DEFAULT_SAMPLES))
    except (TypeError, ValueError):
        samples = _DEFAULT_SAMPLES
    samples = max(10, min(samples, 60))
    try:
        threshold = float(params.get("threshold", _MATCH_THRESHOLD))
    except (TypeError, ValueError):
        threshold = _MATCH_THRESHOLD

    print(f"[FaceAuth] ▶ {action} {name}")
    if player:
        player.write_log(f"[face] {action}")

    try:
        if action == "enroll":
            if not name:
                return "Please tell me the name to enroll this face under."
            return _enroll(name, samples)

        if action in ("verify", "login", "recognize", "recognise"):
            return _verify(threshold)

        if action == "list":
            labels = _load_labels()
            if not labels:
                return "No faces are enrolled yet."
            return "Enrolled faces: " + ", ".join(sorted(labels.values())) + "."

        if action == "remove":
            if not name:
                return "Please tell me which name to remove."
            labels = _load_labels()
            ids = [k for k, v in labels.items() if v.lower() == name.lower()]
            if not ids:
                return f"'{name}' is not enrolled."
            import shutil
            for pid in ids:
                labels.pop(pid, None)
                shutil.rmtree(_data_dir() / "samples" / str(pid), ignore_errors=True)
            _save_labels(labels)
            _retrain()  # rebuild without the removed person
            return f"Removed {name} from enrolled faces."

        return f"Unknown face action: '{action}'. Use enroll, verify, list, or remove."
    except Exception as e:
        print(f"[FaceAuth] ❌ {e}")
        return f"Face {action} failed: {e}"
