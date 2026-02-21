# ──────────────────────────────────────────────
# Trading Bot – root-level commands
# ──────────────────────────────────────────────

.PHONY: dev dev-back dev-front stop docker docker-stop install

# ── Development (local) ──────────────────────

## Start both backend and frontend in parallel
dev:
	@echo "Starting backend and frontend..."
	@make -j2 dev-back dev-front

## Start only the backend (uvicorn)
dev-back:
	cd backend && source venv/bin/activate && python -m uvicorn main:app --reload 2>&1

## Start only the frontend (vite)
dev-front:
	cd frontend && npm run dev

## Install all dependencies
install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

# ── Docker ───────────────────────────────────

## Start both services with Docker Compose
docker:
	docker compose up --build

## Stop Docker Compose services
docker-stop:
	docker compose down
