.PHONY: run up down clean psql agents-only bronze-only

# ── One-command setup and run ──
run:
	docker-compose up -d
	@echo "Waiting for PostgreSQL to be ready..."
	@sleep 3
	python3 src/main.py

# ── Docker lifecycle ──
up:
	docker-compose up -d

down:
	docker-compose down

clean:
	docker-compose down -v

# ── Pipeline stages (after docker-compose up) ──
bronze-only:
	python3 src/main.py --bronze-only

agents-only:
	python3 src/main.py --skip-agents

# ── Connect to PostgreSQL ──
psql:
	docker exec -it medallion-pg psql -U medallion

# ── Install dependencies ──
install:
	pip3 install -r requirements.txt
