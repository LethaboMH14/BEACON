# BEACON — 03 Vision + ML (Sali's spec)

> Owner: Sali. Status: v1.0, 2026-07-24. Day-one doc: `team/SALI.md`.

## 1. What "fine-tuning" means here (priority order)

You do NOT need to train anything from scratch. Every capability starts from a pretrained model that already works, and your job is: run it → evaluate it → fine-tune only where the demo needs it → calibrate thresholds.

| Priority | Capability | Base model | Fine-tune? |
|---|---|---|---|
| P0 | Person + vehicle detection | YOLOv8n (COCO pretrained) | No — works out of the box |
| P0 | Face detect + embed | InsightFace `buffalo_l` (RetinaFace + ArcFace) | No — embed + cosine only |
| P1 | License plate detect + read | YOLOv8 plate weights (community) + EasyOCR | Light — SA plate formats (see §4) |
| P1 | Weapon detection (gun, knife) | YOLOv8s fine-tuned on open weapon datasets | YES — this is your fine-tune showcase |
| P2 | Vehicle make/colour | CLIP zero-shot tags or a small VMMR head | Only if time allows |
| P2 | Audio (gunshot/glass) | YAMNet (VUKA port — already have weights + class map) | No |

## 2. Environment (get running in 30 min)

```
pip install ultralytics insightface onnxruntime easyocr opencv-python
yolo predict model=yolov8n.pt source=0 show=True   # webcam smoke test — do this FIRST
```
If `insightface` fights on Windows, `pip install insightface --no-build-isolation` or fall back to `deepface` (ArcFace backend) — same embeddings, easier install.

## 3. Weapon fine-tune (your headline)

1. Data: Roboflow Universe weapon datasets (search "weapon detection", "gun knife detection" — several thousand labelled images, YOLO format export). Merge 2–3, dedupe, keep classes {handgun, rifle, knife}.
2. Add **hard negatives**: phones, drills, umbrellas, hairbrushes held like weapons — the known false-positive traps. This is what makes your eval slide credible.
3. Train: `yolo train model=yolov8s.pt data=weapons.yaml epochs=50 imgsz=640` — hours on Colab/Kaggle free GPU, feasible today.
4. Eval: confusion matrix + precision/recall ON THE HARD NEGATIVES. Report honestly: "weapon-candidate detector, precision X on our validation set — always fused, never solo" (D10).
5. Register weights in `vision/models/models.json` (name, sha256, size) and hand to Lethabo for the agent.

## 4. Plates — SA specifics

SA formats vary by province (e.g. Gauteng `XX 00 XX GP`, custom plates). EasyOCR gives raw text; add a per-province regex validator + the confusion-aware comparator (0↔O, 1↔I, 8↔B — implemented in `brain/`, you just emit raw text + confidence). Test set: photograph printed plates (make fake ones — do NOT collect real strangers' plates for the repo).

## 5. Faces — thresholds + bias (your second headline)

- Pipeline: RetinaFace detect → align → ArcFace 512-d embed → cosine vs entity store.
- Calibrate on a validation set that looks like South Africa: use balanced public sets, and OUR OWN faces (team consents) across lighting (load-shedding-dark frames included — use low-light augmentation).
- Produce the reliability curve that sets candidate=0.55 / verify-suggest=0.65 (or whatever the data says — those are targets).
- One slide: NIST FRVT found false-positive differentials up to ~100× across demographics; BEACON's answer is architecture (human gate, ADR-0002), not a claim that our model is magically unbiased. You present this — it will land harder than any accuracy number.

## 6. Presentation + Discovery alignment (your other hat)

- Own the 30% slide deck: business case (with Ndu, docs/05), your fine-tune/eval slides, the honesty/bias slide.
- Fold in your 25-page Discovery research: shared-value loop → "Vitality Protect" framing; ecosystem integration points (Insure, Bank, Vitality); the standalone-app-integrating-via-API stance from the July 15 meeting.
- Whisper/KWS work from VUKA: park it — it returns on the roadmap slide as the personal-safety layer (UMKHUSELI integration), not in this build.

## 7. Definition of done

- [ ] G0 (12:00): YOLOv8n live on your webcam; weapon dataset assembled; Colab training started
- [ ] G1: weapon weights v1 + eval on hard negatives; face embed pipeline running; thresholds drafted
- [ ] G2: models registered + integrated in `vision/agent.py` with Lethabo; eval slides done
- [ ] G3: present vision + alignment sections in the pitch
