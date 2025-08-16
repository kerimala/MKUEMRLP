# NSG Extraction Tool Makefile

.PHONY: help setup install clean test lint format run-pipeline dev-install check

# Default target
help:
	@echo "NSG Extraction Tool - Available commands:"
	@echo ""
	@echo "Setup and Installation:"
	@echo "  setup          Create virtual environment and install dependencies"
	@echo "  install        Install package in development mode"
	@echo "  dev-install    Install with development dependencies"
	@echo ""
	@echo "Development:"
	@echo "  test           Run tests (when available)"
	@echo "  lint           Run linting (mypy, black --check, isort --check)"
	@echo "  format         Format code (black, isort)"
	@echo "  check          Run all checks (lint + test)"
	@echo ""
	@echo "Pipeline:"
	@echo "  run-pipeline   Run complete extraction pipeline (requires data/pdfs/)"
	@echo "  pack           Convert PDFs to chunks"
	@echo "  run            Process chunks with DeepSeek API"
	@echo "  merge          Merge chunk results"
	@echo "  propose        Generate proposals"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean          Remove generated files and caches"
	@echo "  clean-all      Remove everything including virtual environment"

# Setup virtual environment and install
setup:
	@echo "🚀 Setting up NSG Extraction Tool..."
	@./setup.sh

# Install package in development mode
install:
	@echo "📦 Installing nsgx package..."
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found. Run 'make setup' first."; exit 1; fi
	@. venv/bin/activate && pip install -e .

# Install with development dependencies
dev-install:
	@echo "🔧 Installing development dependencies..."
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found. Run 'make setup' first."; exit 1; fi
	@. venv/bin/activate && pip install -e ".[dev]"

# Run tests (placeholder for when tests are added)
test:
	@echo "🧪 Running tests..."
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found. Run 'make setup' first."; exit 1; fi
	@echo "⚠️  No tests configured yet. Add pytest tests to enable this target."
	# @. venv/bin/activate && pytest

# Lint code
lint:
	@echo "🔍 Running linting..."
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found. Run 'make setup' first."; exit 1; fi
	@. venv/bin/activate && \
		echo "Running mypy..." && mypy nsgx --ignore-missing-imports || true && \
		echo "Running black --check..." && black --check nsgx && \
		echo "Running isort --check..." && isort --check-only nsgx

# Format code
format:
	@echo "✨ Formatting code..."
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found. Run 'make setup' first."; exit 1; fi
	@. venv/bin/activate && \
		echo "Running black..." && black nsgx && \
		echo "Running isort..." && isort nsgx

# Run all checks
check: lint test
	@echo "✅ All checks completed"

# Complete pipeline
run-pipeline: pack run merge propose
	@echo "🎉 Complete pipeline finished!"

# Individual pipeline steps
pack:
	@echo "📄 Converting PDFs to chunks..."
	@if [ ! -d "data/pdfs" ]; then echo "❌ data/pdfs directory not found. Add PDF files first."; exit 1; fi
	@. venv/bin/activate && nsgx pack --pdfdir data/pdfs

run:
	@echo "🤖 Processing chunks with DeepSeek API..."
	@if [ ! -f ".env" ]; then echo "❌ .env file not found. Copy .env.example and configure API credentials."; exit 1; fi
	@. venv/bin/activate && nsgx run --concurrency 4

merge:
	@echo "🔗 Merging chunk results..."
	@. venv/bin/activate && nsgx merge

propose:
	@echo "📊 Generating proposals..."
	@. venv/bin/activate && nsgx propose

# Clean generated files
clean:
	@echo "🧹 Cleaning generated files..."
	@rm -rf out/ logs/ review/ dbml_patches/
	@rm -f *.jsonl *.csv CHANGELOG.md model_update_proposal.md propose_summary.json
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Clean everything including virtual environment
clean-all: clean
	@echo "🗑️  Removing virtual environment..."
	@rm -rf venv/
	@echo "✅ Cleaned everything. Run 'make setup' to start over."

# Create data directory structure
init-data:
	@echo "📁 Creating data directory structure..."
	@mkdir -p data/pdfs
	@echo "✅ Created data/pdfs/ - copy your PDF files here"

# Verify environment and configuration
verify:
	@echo "🔍 Verifying environment..."
	@if [ ! -d "venv" ]; then echo "❌ Virtual environment not found"; exit 1; fi
	@if [ ! -f ".env" ]; then echo "⚠️  .env file not found"; else echo "✅ .env file exists"; fi
	@if [ ! -d "data/pdfs" ]; then echo "⚠️  data/pdfs directory not found"; else echo "✅ data/pdfs directory exists"; fi
	@. venv/bin/activate && echo "✅ Virtual environment OK" && nsgx --help > /dev/null && echo "✅ nsgx command available"

# Show current status
status:
	@echo "📊 Project Status:"
	@echo "Virtual environment: $(if $(wildcard venv/),✅ Present,❌ Missing)"
	@echo "Configuration file:  $(if $(wildcard .env),✅ Present,❌ Missing)"
	@echo "Data directory:      $(if $(wildcard data/pdfs/),✅ Present,❌ Missing)"
	@echo "Output directory:    $(if $(wildcard out/),✅ Present,❌ Missing)"
	@if [ -f "out/chunks.jsonl" ]; then echo "Chunks file:         ✅ Present"; else echo "Chunks file:         ❌ Missing"; fi
	@if [ -d "out/chunk_results" ]; then echo "Chunk results:       ✅ Present"; else echo "Chunk results:       ❌ Missing"; fi
	@if [ -d "out/docs" ]; then echo "Document results:    ✅ Present"; else echo "Document results:    ❌ Missing"; fi
	@if [ -f "review/candidates_review.csv" ]; then echo "Proposals:           ✅ Present"; else echo "Proposals:           ❌ Missing"; fi