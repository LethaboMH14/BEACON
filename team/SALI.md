# Sali — vision ML + presentation + Discovery alignment

**Mission:** the eyes. Weapon fine-tune is your engineering headline; the bias-aware face pipeline is your credibility headline; the Discovery alignment section of the pitch is your business headline. Full technical spec: docs/03.

## By 12:00 (G0)
- [ ] `pip install ultralytics` → `yolo predict model=yolov8n.pt source=0 show=True` — person boxes on YOUR webcam (10 min, do it first, send the team a screenshot — it's the morale unlock)
- [ ] Assemble weapon dataset from Roboflow Universe (gun/knife, YOLO format) + start collecting hard negatives (phones, drills)
- [ ] Kick off YOLOv8s weapon training on Colab/Kaggle free GPU

## Then
- G1: weapon weights v1 + honest eval (precision/recall ON the hard negatives); InsightFace embed pipeline running; draft face thresholds
- G2: register models in `vision/models/models.json` (sha256), integrate with Lethabo into `agent.py`; low-light (load-shedding) augmentation pass; eval slides
- G3: present: fine-tune story, the NIST-FRVT bias slide + human-gate answer, Discovery shared-value alignment from your research doc

## Notes
- Your Whisper/Common Voice work is NOT wasted — it's the personal-safety layer on the roadmap slide (UMKHUSELI integration). Park, don't delete.
- Faces in the demo: TEAM faces only, consented, said out loud in the pitch. No stranger data anywhere near the repo.
- If InsightFace fights Windows, fall back to deepface(ArcFace) — don't burn hours on a build error.
