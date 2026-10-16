"""Vehicle detection + multi-object tracking for CCTV clips. Runs on a Modal GPU (viz/lab/app.py).

Licences (commercial use OK):
  detector  RT-DETR, Hugging Face `PekingU/rtdetr_r50vd_coco_o365`, Apache-2.0 (model card),
            loaded with `transformers` (Apache-2.0). Ultralytics YOLO is NOT used (AGPL-3.0).
  tracker   ByteTrack from `supervision` (MIT).

Privacy (responsible design):
  - Only vehicle boxes are tracked. We never read number plates or faces (no OCR, no face model).
  - Persons are detected ONLY so they can be blurred in every frame we show or export.
  - Optional plate-zone blur: the lower-middle band of every vehicle box, where plates sit.
  - The raw video stays in the Modal volume; only blurred stills leave it.
  - The video file is untrusted input: decoded by OpenCV in an isolated container, never executed.

Output (tracks.json):
  {"fps", "width", "height", "n_frames", "stride", "model", "tracker",
   "tracks": {"<id>": {"cls", "frames": [...], "boxes": [[x1,y1,x2,y2]...], "conf": [...]}},
   "persons": {"<frame>": [[x1,y1,x2,y2], ...]}}
Ground contact point used downstream = bottom-centre of each vehicle box.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

MODEL_ID = "PekingU/rtdetr_r50vd_coco_o365"
MODEL_LICENCE = "Apache-2.0"
VEHICLE_CLASSES = ("car", "truck", "bus", "motorcycle")
PERSON_CLASS = "person"
# DESIGN ASSUMPTIONS for the detector / tracker.
SCORE_THRESHOLD = 0.2          # low-score boxes feed ByteTrack's second association pass
TRACK_ACTIVATION = 0.4      # a NEW track needs a confident detection
MAX_FRAMES = 3000          # longer clips are subsampled with a stride
MIN_TRACK_FRAMES = 8
BATCH = 8
NMS_IOU = 0.8              # class-agnostic NMS: only near-identical boxes (car+truck on one object)
EDGE_PX = 3                # boxes within this of the frame edge are truncated


def truncated(box, W: int, H: int, edge: int = EDGE_PX) -> bool:
    """Vehicle box cut by the image border (bottom or sides): contact point unreliable."""
    x1, y1, x2, y2 = box
    return y2 >= H - edge or x1 <= edge or x2 >= W - edge


def plate_zone(box) -> tuple[int, int, int, int]:
    """Lower-middle band of a vehicle box (front or rear plate area)."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    return int(x1 + 0.2 * w), int(y1 + 0.55 * h), int(x2 - 0.2 * w), int(y2)


def privacy_blur(frame: np.ndarray, persons=(), vehicles=(), plates: bool = True) -> np.ndarray:
    """Blur persons (whole box, padded) and optionally plate zones of vehicles. Returns a copy."""
    import cv2
    out = frame.copy()
    H, W = out.shape[:2]
    regions = []
    for x1, y1, x2, y2 in persons:
        px, py = 0.15 * (x2 - x1), 0.1 * (y2 - y1)
        regions.append((int(x1 - px), int(y1 - py), int(x2 + px), int(y2 + py)))
    if plates:
        regions += [plate_zone(b) for b in vehicles]
    for x1, y1, x2, y2 in regions:
        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(W, x2), min(H, y2)
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue
        roi = out[y1:y2, x1:x2]
        k = max(15, (max(x2 - x1, y2 - y1) // 3) | 1)
        small = cv2.resize(roi, (max(1, (x2 - x1) // 12), max(1, (y2 - y1) // 12)), interpolation=cv2.INTER_AREA)
        out[y1:y2, x1:x2] = cv2.GaussianBlur(cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST), (k, k), 0)
    return out


def detect_and_track(video_path: str, out_dir: str, model_id: str = MODEL_ID, threshold: float = SCORE_THRESHOLD,
                     plates: bool = True, device: str | None = None) -> dict:
    import cv2
    import supervision as sv
    import torch
    from transformers import RTDetrForObjectDetection, RTDetrImageProcessor

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("could not decode the video")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not (1 <= fps <= 240) or W < 64 or H < 64:
        raise ValueError(f"unsupported video (fps={fps}, size={W}x{H})")
    stride = max(1, math.ceil(n / MAX_FRAMES)) if n > 0 else 1

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    proc = RTDetrImageProcessor.from_pretrained(model_id)
    model = RTDetrForObjectDetection.from_pretrained(model_id).to(device).eval()
    id2label = {int(k): v.lower() for k, v in model.config.id2label.items()}
    veh_ids = {k for k, v in id2label.items() if v in VEHICLE_CLASSES}
    person_ids = {k for k, v in id2label.items() if v == PERSON_CLASS}
    tracker = sv.ByteTrack(track_activation_threshold=TRACK_ACTIVATION, frame_rate=max(1, round(fps / stride)),
                           lost_track_buffer=max(10, round(fps / stride)))

    tracks: dict[int, dict] = defaultdict(lambda: {"cls": [], "frames": [], "boxes": [], "conf": []})
    persons: dict[int, list] = {}
    first_frame = None
    best = {}                                 # track id -> (area, frame idx)
    frames_buf, idx_buf = [], []
    fi = -1
    n_done = 0

    def flush():
        nonlocal n_done
        if not frames_buf:
            return
        rgb = [cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in frames_buf]
        inputs = proc(images=rgb, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        sizes = torch.tensor([[f.shape[0], f.shape[1]] for f in frames_buf], device=device)
        res = proc.post_process_object_detection(outputs, target_sizes=sizes, threshold=threshold)
        for k, r in zip(idx_buf, res):
            boxes = r["boxes"].float().cpu().numpy()
            scores = r["scores"].float().cpu().numpy()
            labels = r["labels"].cpu().numpy()
            pm = np.isin(labels, list(person_ids))
            if pm.any():
                persons[k] = boxes[pm].round(1).tolist()
            vm = np.isin(labels, list(veh_ids))
            det = sv.Detections(xyxy=boxes[vm], confidence=scores[vm], class_id=labels[vm].astype(int))
            if len(det):
                # One box per vehicle: the detector often fires car + truck/bus on the same object.
                det = det.with_nms(threshold=NMS_IOU, class_agnostic=True)
            det = tracker.update_with_detections(det)
            for b, c, cl, tid in zip(det.xyxy, det.confidence, det.class_id, det.tracker_id):
                if truncated(b, W, H):
                    continue   # box cut by the frame edge: its bottom-centre is not the road contact point
                tr = tracks[int(tid)]
                tr["cls"].append(id2label[int(cl)])
                tr["frames"].append(k)
                tr["boxes"].append([round(float(v), 2) for v in b])
                tr["conf"].append(round(float(c), 3))
                area = (b[2] - b[0]) * (b[3] - b[1])
                if area > best.get(int(tid), (0, 0))[0]:
                    best[int(tid)] = (float(area), k)
        n_done += len(frames_buf)
        frames_buf.clear()
        idx_buf.clear()

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        fi += 1
        if fi % stride:
            continue
        if first_frame is None:
            first_frame = frame.copy()
        frames_buf.append(frame)
        idx_buf.append(fi)
        if len(frames_buf) >= BATCH:
            flush()
    flush()
    cap.release()
    if first_frame is None:
        raise ValueError("no frames decoded")

    keep = {tid: t for tid, t in tracks.items() if len(t["frames"]) >= MIN_TRACK_FRAMES}
    out_tracks = {str(tid): {"cls": Counter(t["cls"]).most_common(1)[0][0], "frames": t["frames"],
                             "boxes": t["boxes"], "conf": t["conf"]} for tid, t in keep.items()}

    def boxes_at(k):
        return [t["boxes"][t["frames"].index(k)] for t in keep.values() if k in t["frames"]]

    # Calibration still: first processed frame, privacy-blurred.
    k0 = 0
    cv2.imwrite(str(out / "frame0.jpg"), privacy_blur(first_frame, persons.get(k0, []), boxes_at(k0), plates),
                [cv2.IMWRITE_JPEG_QUALITY, 88])
    # Thumbnails: each kept track at its largest box, blurred.
    want = {best[tid][1]: [] for tid in keep if tid in best}
    for tid in keep:
        if tid in best:
            want[best[tid][1]].append(tid)
    cap = cv2.VideoCapture(video_path)
    fi = -1
    thumbs = {}
    while want:
        ok, frame = cap.read()
        if not ok:
            break
        fi += 1
        if fi not in want:
            continue
        safe = privacy_blur(frame, persons.get(fi, []), boxes_at(fi), plates)
        for tid in want.pop(fi):
            x1, y1, x2, y2 = keep[tid]["boxes"][keep[tid]["frames"].index(fi)]
            pw, ph = 0.25 * (x2 - x1), 0.25 * (y2 - y1)
            crop = safe[max(0, int(y1 - ph)):min(H, int(y2 + ph)), max(0, int(x1 - pw)):min(W, int(x2 + pw))]
            if crop.size:
                s = 160 / max(crop.shape[:2])
                crop = cv2.resize(crop, (max(1, int(crop.shape[1] * s)), max(1, int(crop.shape[0] * s))))
                cv2.imwrite(str(out / f"track_{tid}.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
                thumbs[str(tid)] = True
    cap.release()

    result = {"fps": fps, "width": W, "height": H, "n_frames": fi + 1 if n <= 0 else n, "stride": stride,
              "frames_processed": n_done, "model": f"{model_id} ({MODEL_LICENCE})", "tracker": "ByteTrack (supervision, MIT)",
              "threshold": threshold, "plates_blurred": plates, "tracks": out_tracks,
              "persons": {str(k): v for k, v in persons.items()}, "thumbs": sorted(thumbs, key=int)}
    (out / "tracks.json").write_text(json.dumps(result, separators=(",", ":")))
    return {k: v for k, v in result.items() if k not in ("tracks", "persons")} | {
        "n_tracks": len(out_tracks), "n_person_frames": len(persons)}
