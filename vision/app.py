from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from inference_sdk import InferenceHTTPClient
from dotenv import load_dotenv

import shutil
import os
import uuid

load_dotenv()

app = FastAPI(title="Weapon Detection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key = os.getenv("ROBOFLOW_API_KEY")

if api_key is None:
    raise Exception("ROBOFLOW_API_KEY not found.")

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=api_key
)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.get("/")
def home():
    return {
        "message": "Weapon Detection API Running"
    }


@app.post("/detect")
async def detect_weapon(file: UploadFile = File(...)):

    extension = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{extension}"

    filepath = os.path.join(UPLOAD_FOLDER, filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:

        result = client.run_workflow(
            workspace_name="mbaye-salimata-icloud-com",
            workflow_id="weapon-detection-alerts-1784956355975",
            images={
                "image": filepath
            },
            use_cache=True
        )

        return result

    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if os.path.exists(filepath):
            os.remove(filepath)