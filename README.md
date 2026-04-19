# LocalScript Lua Agent

Локальная агентская система для генерации Lua-кода в среде MWS Octapi.

## Требования

- Docker 20.10+
- Docker Compose 2.0+
- NVIDIA GPU с драйверами >= 525
- NVIDIA Container Toolkit
- 8+ GB свободной VRAM

## Быстрый старт

# 1. Клонировать репозиторий

```bash
git clone https://git.truetecharena.ru/tta/true-tech-hack2026-localscript/players/task-repo.git
cd task-repo
```

# 2. Запуск сервера Ollama на хосте
```bash
ollama serve
ollama pull deepseek-coder:6.7b-instruct-q4_K_M
```

# 3. Запуск локальной агентской системы

```bash
docker compose up -d --build
```

# 4. Проверить работоспособность локальной агентской системы

```bash
curl http://localhost:8080/health
```

# 5. Отправить тестовый запрос

```bash
curl -X POST http://localhost:8080/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Из полученного списка email получи последний"}'
```