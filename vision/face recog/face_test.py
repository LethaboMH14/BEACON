import cv2
import insightface

# Load InsightFace model
app = insightface.app.FaceAnalysis()
app.prepare(ctx_id=-1, det_size=(640, 640))  # CPU

# Load image
image = cv2.imread("person3.jpeg")

if image is None:
    raise FileNotFoundError("Could not find person3.jpeg")

# Detect faces
faces = app.get(image)

print(f"Detected {len(faces)} face(s)\n")

for i, face in enumerate(faces):
    print(f"Face {i+1}")
    print("Bounding Box:", face.bbox)
    print("Gender:", "Male" if face.gender == 1 else "Female")
    print("Embedding Length:", len(face.embedding))
    print()

    x1, y1, x2, y2 = face.bbox.astype(int)

    cv2.rectangle(image, (x1, y1), (x2, y2), (0,255,0), 2)
    cv2.putText(
        image,
        f"Face {i+1}",
        (x1, y1-10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0,255,0),
        2
    )

# Save result
cv2.imwrite("detected_faces.jpeg", image)

print("Saved detected_faces.jpeg")