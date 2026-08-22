from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.routers import repos, graph, chat

app = FastAPI(title="CodeAtlas AI Backend")

# Allow requests from the Next.js frontend during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(repos.router)
app.include_router(graph.router)
app.include_router(chat.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
