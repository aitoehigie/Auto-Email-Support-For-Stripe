#!/bin/bash

set -e

# Directory setup
APP_DIR="$HOME/.payment_update_system"
CURRENT_DIR="$(pwd)"

# Check if we're already in the app directory
if [ "$CURRENT_DIR" = "$APP_DIR" ]; then
    echo "Already in the application directory."
else
    mkdir -p "$APP_DIR"
    
    # Copy the entire project structure
    echo "Copying project files..."
    # Create the destination if it doesn't exist
    mkdir -p "$APP_DIR"
    
    # Copy all Python files, directories, and requirements.txt
    cp -r ./*.py ./*/ "$APP_DIR/" 2>/dev/null || echo "No files found to copy."
    if [ -f "requirements.txt" ]; then
        cp requirements.txt "$APP_DIR/"
    fi
    
    echo "Moving to application directory..."
fi

# Change to the app directory
cd "$APP_DIR"

# Install uv if not present
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Check if uv is working
if ! uv --version &> /dev/null; then
    echo "Failed to install uv. Please install it manually from https://github.com/astral-sh/uv"
    exit 1
fi

# Install Python 3.11 if not available (uv picks a sensible default)
echo "Ensuring Python is installed..."
uv python install 3.11

# Create a virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
else
    echo "Using existing virtual environment."
fi

# Install dependencies
echo "Installing dependencies..."
if [ -f "requirements.txt" ]; then
    uv pip install -r requirements.txt
else
    echo "Warning: requirements.txt not found. Dependencies may not be installed correctly."
fi

# Create logs directory if it doesn't exist
echo "Setting up logs directory..."
mkdir -p "logs"
echo "Log directory created at: $APP_DIR/logs"

# Create a .env file if not present (user must fill this in)
if [ ! -f ".env" ]; then
    cat <<EOF > .env
EMAIL_SERVER=imap.gmail.com
EMAIL_USER=your_email@gmail.com
EMAIL_PASS=your_password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
STRIPE_API_KEY=your_stripe_key
NLP_API_KEY=your_anthropic_key
CONFIDENCE_THRESHOLD=0.9
EOF
    echo "Please edit .env with your credentials."
    echo "You can do this by running: nano $APP_DIR/.env"
    exit 0
fi

# Run the application
echo "Starting the Payment Update System..."
uv run python main.py