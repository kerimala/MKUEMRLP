#!/bin/bash

# NSG Extraction Tool Setup Script
# Creates virtual environment and installs dependencies

set -e  # Exit on any error

echo "🚀 Setting up NSG Extraction Tool..."

# Check if Python 3.10+ is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Error: Python $REQUIRED_VERSION or higher is required. Found: $PYTHON_VERSION"
    exit 1
fi

echo "✅ Python version: $PYTHON_VERSION"

# Create virtual environment
if [ -d "venv" ]; then
    echo "📁 Virtual environment already exists. Removing old one..."
    rm -rf venv
fi

echo "🐍 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip

# Install the package and dependencies
echo "⚙️  Installing nsgx and dependencies..."
pip install -e .

# Copy environment template if .env doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file and add your DeepSeek API credentials!"
else
    echo "📝 .env file already exists"
fi

# Create necessary directories
echo "📁 Creating output directories..."
mkdir -p out logs

# Check if pdftotext is available (optional dependency)
if command -v pdftotext &> /dev/null; then
    echo "✅ pdftotext is available for PDF extraction fallback"
else
    echo "⚠️  pdftotext not found. PDF extraction will use Python libraries only."
    echo "   To install pdftotext on Ubuntu/Debian: sudo apt-get install poppler-utils"
    echo "   To install pdftotext on macOS: brew install poppler"
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "2. Edit .env file with your DeepSeek API credentials:"
echo "   nano .env"
echo ""
echo "3. Test the installation:"
echo "   nsgx --help"
echo ""
echo "4. Run the complete pipeline:"
echo "   nsgx pack --pdfdir ./data/pdfs"
echo "   nsgx run --concurrency 4"
echo "   nsgx merge"
echo "   nsgx propose"
echo ""
echo "📚 For more information, see README.md"