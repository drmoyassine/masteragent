"""
GLiNER2 Entity Recognition Service
A lightweight FastAPI service for Named Entity Recognition using GLiNER2 models.
"""
import os
import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from gliner import GLiNER

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MODEL_NAME = os.environ.get('MODEL_NAME', 'urchade/gliner_multi')

# Initialize FastAPI app
app = FastAPI(
    title="GLiNER2 NER Service",
    description="Named Entity Recognition using GLiNER2 multi-task models",
    version="1.0.0"
)

# Global model variable
model = None

# Request/Response Models
class EntityLabel(BaseModel):
    name: str
    description: Optional[str] = None

class ExtractRequest(BaseModel):
    text: str
    labels: List[str] = ["person", "organization", "location", "date", "product", "event"]
    threshold: float = 0.5

class Entity(BaseModel):
    text: str
    label: str
    start: int
    end: int
    score: float

class ExtractResponse(BaseModel):
    entities: List[Entity]
    text: str
    model: str

class HealthResponse(BaseModel):
    status: str
    model: str
    model_loaded: bool

# Startup event to load model
@app.on_event("startup")
async def load_model():
    global model
    try:
        logger.info(f"Loading GLiNER model: {MODEL_NAME}")
        model = GLiNER.from_pretrained(MODEL_NAME)
        logger.info("GLiNER model loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load GLiNER model: {e}")
        raise

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy" if model is not None else "unhealthy",
        model=MODEL_NAME,
        model_loaded=model is not None
    )

@app.post("/extract", response_model=ExtractResponse)
async def extract_entities(request: ExtractRequest):
    """
    Extract entities from text using GLiNER2.
    
    - **text**: The input text to analyze
    - **labels**: List of entity types to extract (e.g., ["person", "organization"])
    - **threshold**: Minimum confidence score (0.0 to 1.0)
    """
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    if not request.text.strip():
        return ExtractResponse(entities=[], text=request.text, model=MODEL_NAME)
    
    try:
        # Run GLiNER prediction
        predictions = model.predict_entities(
            request.text,
            request.labels,
            threshold=request.threshold
        )
        
        # Format results
        entities = []
        for pred in predictions:
            entities.append(Entity(
                text=pred.get("text", ""),
                label=pred.get("label", ""),
                start=pred.get("start", 0),
                end=pred.get("end", 0),
                score=pred.get("score", 0.0)
            ))
        
        # Sort by position in text
        entities.sort(key=lambda x: x.start)
        
        return ExtractResponse(
            entities=entities,
            text=request.text,
            model=MODEL_NAME
        )
    
    except Exception as e:
        logger.error(f"Entity extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

@app.get("/labels")
async def get_suggested_labels():
    """Get suggested entity labels for common use cases"""
    return {
        "general": ["person", "organization", "location", "date", "time", "money", "product"],
        "business": ["company", "person", "product", "service", "location", "date", "money", "percentage"],
        "legal": ["person", "organization", "law", "court", "date", "location", "case_number"],
        "medical": ["disease", "symptom", "drug", "treatment", "body_part", "test", "doctor"],
        "finance": ["company", "stock", "currency", "amount", "date", "percentage", "index"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
