import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from database import create_document, get_documents, db
from schemas import Generation

app = FastAPI(title="Image Generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response

# -------- Image Generation API (SVG Procedural Placeholder) --------
class GenerateRequest(BaseModel):
    prompt: str
    style: Optional[str] = None
    seed: Optional[int] = None
    width: int = 1024
    height: int = 1024

class GenerateResponse(BaseModel):
    id: str
    prompt: str
    style: Optional[str]
    seed: Optional[int]
    width: int
    height: int
    image_data_url: str
    created_at: datetime

import base64
import random


def svg_from_prompt(prompt: str, seed: Optional[int], width: int, height: int) -> str:
    """Create a playful SVG based on the prompt and seed. Acts as a deterministic placeholder generator."""
    rnd = random.Random(seed or hash(prompt) % (2**32 - 1))
    # Color palette
    colors = [
        "#8b5cf6", "#06b6d4", "#ec4899", "#f59e0b", "#10b981", "#3b82f6"
    ]
    bg = rnd.choice(["#0f172a", "#111827", "#0b1020", "#0a0f1f"]) if (prompt and len(prompt) % 2 == 0) else "#0b1220"
    shapes = []
    for _ in range(18):
        cx = rnd.randint(0, width)
        cy = rnd.randint(0, height)
        r = rnd.randint(20, int(min(width, height) * 0.25))
        color = rnd.choice(colors)
        opacity = rnd.uniform(0.2, 0.8)
        shapes.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" fill-opacity="{opacity}" />')
    text_color = "white"
    safe_prompt = (prompt or "").replace("<", "&lt;").replace(">", "&gt;")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
      <rect width="100%" height="100%" fill="{bg}"/>
      <g filter="url(#blur)"> {''.join(shapes)} </g>
      <defs>
        <filter id="blur"><feGaussianBlur in="SourceGraphic" stdDeviation="20" /></filter>
      </defs>
      <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="{text_color}" font-family="Inter, system-ui" font-size="{min(width,height)//18}" opacity="0.9">{safe_prompt[:48]}</text>
    </svg>'''
    data_url = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return data_url


@app.post("/api/generate", response_model=GenerateResponse)
async def generate_image(req: GenerateRequest):
    if not req.prompt or len(req.prompt.strip()) == 0:
        raise HTTPException(status_code=400, detail="Prompt is required")

    image_data_url = svg_from_prompt(req.prompt.strip(), req.seed, req.width, req.height)

    # Persist to database
    try:
        gen = Generation(
            prompt=req.prompt.strip(),
            style=req.style,
            seed=req.seed,
            width=req.width,
            height=req.height,
            image_data_url=image_data_url,
            tags=None,
        )
        inserted_id = create_document("generation", gen)
    except Exception:
        # If DB not available, still return the image
        inserted_id = "no-db"

    return GenerateResponse(
        id=str(inserted_id),
        prompt=req.prompt.strip(),
        style=req.style,
        seed=req.seed,
        width=req.width,
        height=req.height,
        image_data_url=image_data_url,
        created_at=datetime.utcnow(),
    )


@app.get("/api/generations")
async def list_generations(limit: int = 12):
    """Return recent generations if database is available."""
    try:
        docs = get_documents("generation", {}, limit=limit)
        results = []
        for d in docs:
            item = {
                "id": str(d.get("_id", "")),
                "prompt": d.get("prompt"),
                "style": d.get("style"),
                "seed": d.get("seed"),
                "width": d.get("width"),
                "height": d.get("height"),
                "image_data_url": d.get("image_data_url"),
                "created_at": d.get("created_at").isoformat() if d.get("created_at") else None,
            }
            results.append(item)
        # Newest first if docs aren't already sorted
        results = list(reversed(results))
        return {"items": results}
    except Exception as e:
        # Database not available
        return {"items": []}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
