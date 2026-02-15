.PHONY: help install test format lint type-check clean build all

help:
	@echo "Cube Card Tracker - Development Commands"
	@echo ""
	@echo "Available commands:"
	@echo "  make install      Install dependencies with Poetry"
	@echo "  make test         Run test suite"
	@echo "  make format       Format code with Black and isort"
	@echo "  make lint         Run flake8 linter"
	@echo "  make type-check   Run mypy type checker"
	@echo "  make clean        Remove build artifacts and caches"
	@echo "  make build        Build package with Poetry"
	@echo "  make all          Run format, lint, type-check, and test"

install:
	poetry install

test:
	poetry run pytest

test-cov:
	poetry run pytest --cov=cube_card_tracker --cov-report=html --cov-report=term

format:
	poetry run black src tests examples
	poetry run isort src tests examples

lint:
	poetry run flake8 src tests

type-check:
	poetry run mypy src

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf htmlcov
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build:
	poetry build

all: format lint type-check test
	@echo "All checks passed!"

.DEFAULT_GOAL := help