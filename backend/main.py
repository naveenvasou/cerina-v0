from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from backend.graph import get_compiled_graph
from langchain_core.messages import HumanMessage
from backend.websocket_routes import router as websocket_router
from backend.api.sessions import router as sessions_router
from backend.database import create_tables, init_checkpointer, close_checkpointer
from backend.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - runs on startup/shutdown."""
    # Startup: Create database tables
    if settings.DATABASE_URL:
        print("🗄️ Initializing database...")
        await create_tables()
        print("✅ Database tables ready")
    else:
        print("⚠️ DATABASE_URL not set - skipping database initialization")
    
    # Initialize checkpointer (PostgresSaver or MemorySaver fallback)
    await init_checkpointer()
    
    yield
    
    # Shutdown: cleanup checkpointer connection
    await close_checkpointer()
    print("👋 Shutting down...")


app = FastAPI(lifespan=lifespan)

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://cerina-v0.vercel.app"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(websocket_router)
app.include_router(sessions_router)


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = []


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "database": bool(settings.DATABASE_URL)}


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        # Note: This HTTP endpoint is now secondary to the WebSocket flow
        # mapping simple request to state
        inputs = {"user_query": request.message, "plan": None, "draft": None}
        
        compiled_graph = get_compiled_graph()
        final_state = await compiled_graph.ainvoke(inputs)
        
        return {
            "status": "success", 
            "plan": final_state.get("plan"),
            "draft": final_state.get("draft")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
