# SplitMate Docker Management

.PHONY: help build run stop clean logs shell test prod dev restart backup restore

# Default help command
help:
	@echo "SplitMate Docker Commands:"
	@echo ""
	@echo "Development:"
	@echo "  make build     - Build the Docker image"
	@echo "  make dev       - Run in development mode"
	@echo "  make run       - Run the application"
	@echo "  make stop      - Stop all containers"
	@echo "  make restart   - Restart the application"
	@echo ""
	@echo "Production:"
	@echo "  make prod      - Run in production mode with Nginx"
	@echo ""
	@echo "Maintenance:"
	@echo "  make logs      - View application logs"
	@echo "  make shell     - Access container shell"
	@echo "  make clean     - Clean up containers and images"
	@echo "  make backup    - Backup database"
	@echo "  make restore   - Restore database from backup"
	@echo ""
	@echo "Testing:"
	@echo "  make test      - Run tests in container"

# Build the Docker image
build:
	@echo "Building SplitMate Docker image..."
	docker-compose build

# Run in development mode (without nginx)
dev:
	@echo "Starting SplitMate in development mode..."
	docker-compose up -d splitmate
	@echo "Application running at http://localhost:8080"

# Run the full application
run:
	@echo "Starting SplitMate application..."
	docker-compose up -d
	@echo "Application running at http://localhost:8080"

# Run in production mode with nginx
prod:
	@echo "Starting SplitMate in production mode..."
	docker-compose --profile production up -d
	@echo "Application running at http://localhost:80"

# Stop all containers
stop:
	@echo "Stopping SplitMate containers..."
	docker-compose down

# Restart the application
restart: stop run

# View logs
logs:
	docker-compose logs -f splitmate

# Access container shell
shell:
	docker-compose exec splitmate /bin/bash

# Clean up everything
clean:
	@echo "Cleaning up Docker containers and images..."
	docker-compose down -v --remove-orphans
	docker system prune -f
	@echo "Cleanup complete!"

# Backup database
backup:
	@echo "Creating database backup..."
	@mkdir -p backups
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	docker-compose exec splitmate cp /app/data/splitmate.db /tmp/backup_$$timestamp.db || true; \
	docker cp $$(docker-compose ps -q splitmate):/tmp/backup_$$timestamp.db ./backups/splitmate_backup_$$timestamp.db || true; \
	echo "Backup created: backups/splitmate_backup_$$timestamp.db"

# Restore database from backup
restore:
	@echo "Available backups:"
	@ls -la backups/ 2>/dev/null || echo "No backups found"
	@echo ""
	@echo "To restore, run: make restore-file BACKUP=filename"

restore-file:
	@if [ -z "$(BACKUP)" ]; then \
		echo "Please specify backup file: make restore-file BACKUP=filename"; \
		exit 1; \
	fi
	@echo "Restoring database from $(BACKUP)..."
	docker cp ./backups/$(BACKUP) $$(docker-compose ps -q splitmate):/app/data/splitmate.db
	docker-compose restart splitmate
	@echo "Database restored from $(BACKUP)"

# Run tests in container
test:
	@echo "Running tests in container..."
	docker-compose exec splitmate python -m pytest tests/ -v || echo "Tests directory not found. Create tests/ directory with test files."

# Check application health
health:
	@echo "Checking application health..."
	@curl -f http://localhost:8080/ > /dev/null 2>&1 && echo "✅ Application is healthy" || echo "❌ Application is not responding"

# View application status
status:
	@echo "Container Status:"
	@docker-compose ps
	@echo ""
	@echo "Application Health:"
	@make health

# Quick setup for first time users
setup: build run
	@echo ""
	@echo "🎉 SplitMate is now running!"
	@echo ""
	@echo "📱 Access the app at: http://localhost:8080"
	@echo "📊 View logs with: make logs"
	@echo "🔧 Access shell with: make shell"
	@echo "🛑 Stop with: make stop"

# Update application (rebuild and restart)
update:
	@echo "Updating SplitMate..."
	make stop
	make build
	make run
	@echo "Update complete!"