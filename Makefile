.PHONY: run up down clean psql pipeline-only bronze-only

# ── One-command setup and run ──
run:
	docker compose up -d --wait
	python3 src/main.py

# ── Docker lifecycle ──
up:
	docker compose up -d

down:
	docker compose down

clean:
	docker compose down -v

# ── Pipeline stages (after docker-compose up) ──
bronze-only:
	python3 src/main.py --bronze-only

pipeline-only:
	python3 src/main.py --skip-agents

# ── Connect to PostgreSQL ──
psql:
	docker exec -it medallion-pg psql -U medallion

# ── Install dependencies ──
install:
	pip3 install -r requirements.txt
