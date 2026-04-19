# api.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from orchestrator import AgentOrchestrator
from contracts import GenerateRequest, GenerateResponse
import uvicorn
import os
import requests

app = FastAPI(
    title="MWS Octapi Lua Agent System",
    description="Локальная агентская система для генерации Lua-кода",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
model_name = os.getenv("MODEL_NAME", "deepseek-coder:6.7b-instruct-q4_K_M")

# Глобальный оркестратор
orchestrator = AgentOrchestrator(
    ollama_url=ollama_url
)

@app.post("/generate", response_model=GenerateResponse)
async def generate_lua(request: GenerateRequest):
    """
    Генерация Lua-кода по описанию задачи
    
    Система использует агентный подход:
    1. Анализирует задачу и строит план
    2. Генерирует первоначальный код
    3. Проверяет и критикует результат
    4. Итеративно улучшает код
    """
    # Проверка 1: Доступен ли Ollama
    if not _check_ollama():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Ollama service is not accessible",
                "details": f"Cannot connect to {ollama_url}",
                "solution": "Ensure Ollama is running: docker-compose up -d ollama"
            }
        )

    # Проверка 2: Загружена ли модель
    if not _check_model_loaded():
        raise HTTPException(
            status_code=503,
            detail={
                "error": f"Model '{model_name}' is not loaded"
            }
        )

    try:
        response = orchestrator.process(request)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Code generation failed",
                "details": str(e),
                "solution": "Check the prompt and try again"
            }
        )

@app.get("/health")
async def health_check():
    """Проверка работоспособности"""
    return {
        "status": "healthy",
        "ollama": "connected" if _check_ollama() else "disconnected",
        "model": model_name
    }

def _check_ollama() -> bool:
    try:
        r = requests.get(f"{ollama_url}/api/tags", timeout=5)
        return r.status_code == 200
    except:
        return False

def _check_model_loaded() -> bool:
    """Проверка, что нужная модель загружена в Ollama"""
    try:
        response = requests.get(f"{ollama_url}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            for model in models:
                if model_name in model.get("name", ""):
                    return True
        return False
    except:
        return False

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
