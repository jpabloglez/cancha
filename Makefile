# Makefile for the basquets Docker Compose stack.
# Run `make` or `make help` to list available targets.
#
# Per-service pattern targets (services: backend frontend worker db redis):
#   make logs-<service>     Follow logs from one service
#   make restart-<service>  Restart one service
#   make stop-<service>     Stop one service
#   make start-<service>    Start one service
#   make shell-<service>    Open a bash shell in a service container

COMPOSE := docker compose

.DEFAULT_GOAL := help
.PHONY: help build up up-build down stop start restart logs ps images \
        migrate makemigrations seed superuser shell djshell test lint \
        clean prune

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Per-service targets (services: backend frontend worker db redis):"
	@printf "  \033[36m%-20s\033[0m %s\n" "logs-<service>"    "Follow logs, e.g. make logs-backend"
	@printf "  \033[36m%-20s\033[0m %s\n" "restart-<service>" "Restart one service, e.g. make restart-backend"
	@printf "  \033[36m%-20s\033[0m %s\n" "stop-<service>"    "Stop one service, e.g. make stop-worker"
	@printf "  \033[36m%-20s\033[0m %s\n" "start-<service>"   "Start one service, e.g. make start-worker"
	@printf "  \033[36m%-20s\033[0m %s\n" "shell-<service>"   "Bash shell in a container, e.g. make shell-frontend"

## --- Compose lifecycle ---------------------------------------------------

build: ## Build the basquets-backend and basquets-frontend images
	$(COMPOSE) build

up: ## Start all services in the background
	$(COMPOSE) up -d

up-build: ## Rebuild images and start all services in the background
	$(COMPOSE) up -d --build

down: ## Stop and remove containers and networks
	$(COMPOSE) down

stop: ## Stop all services without removing containers
	$(COMPOSE) stop

start: ## Start all previously-stopped services
	$(COMPOSE) start

restart: ## Restart all services
	$(COMPOSE) restart

ps: ## Show service status
	$(COMPOSE) ps

logs: ## Follow logs from all services
	$(COMPOSE) logs -f --tail=100

images: ## List the locally built basquets images
	docker images 'basquets-*'

## --- Per-service pattern targets -----------------------------------------
## Syntax: make <action>-<service>  (e.g. make logs-backend)

logs-%:
	$(COMPOSE) logs -f --tail=100 $*

restart-%:
	$(COMPOSE) restart $*

stop-%:
	$(COMPOSE) stop $*

start-%:
	$(COMPOSE) start $*

shell-%:
	$(COMPOSE) exec $* bash

## --- Backend tasks (require the stack to be up) --------------------------

migrate: ## Apply Django migrations
	$(COMPOSE) exec backend python manage.py migrate

makemigrations: ## Generate Django migrations
	$(COMPOSE) exec backend python manage.py makemigrations

seed: ## Load deterministic demo data
	$(COMPOSE) exec backend python manage.py seed_demo_data

superuser: ## Create a Django admin superuser
	$(COMPOSE) exec backend python manage.py createsuperuser

shell: ## Open a bash shell in the backend container
	$(COMPOSE) exec backend bash

djshell: ## Open a Django shell in the backend container
	$(COMPOSE) exec backend python manage.py shell

test: ## Run the backend test suite
	$(COMPOSE) exec backend pytest

lint: ## Run ruff on the backend
	$(COMPOSE) exec backend ruff check .

## --- Cleanup -------------------------------------------------------------

clean: ## Stop and remove containers, networks and volumes (drops the DB)
	$(COMPOSE) down -v --remove-orphans

prune: clean ## Also remove the locally built basquets images
	-docker rmi basquets-backend basquets-frontend
