#!/bin/bash
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; exit 1; }
print_info() { echo -e "${BLUE}→${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }

echo "========================================="
echo "  RAG System - Setup"
echo "========================================="

print_info "Checking Docker..."
docker info > /dev/null 2>&1 || print_error "Docker not running - please start Docker first"
print_success "Docker is running"

print_info "Checking configuration..."
[ ! -f .env ] && print_error ".env file missing - copy env.example to .env and configure settings"
print_success "Configuration found"

# Lade .env Variablen
source .env 2>/dev/null || true
LLM_MODEL=${LLM_MODEL:-llama2}
LLM_PROVIDER=${LLM_PROVIDER:-ollama}

mkdir -p backend/data backend/models

print_info "Starting RAG System..."
docker-compose up -d --build

echo ""
print_success "Services started"

# Wenn Ollama als Provider konfiguriert ist, prüfe und lade Modell
if [ "$LLM_PROVIDER" = "ollama" ]; then
    print_info "Ollama Provider detected - checking model '$LLM_MODEL'..."

    # Warte auf Ollama
    print_info "Waiting for Ollama to be ready..."
    RETRY_COUNT=0
    MAX_RETRIES=30
    until docker exec rag-ollama ollama list > /dev/null 2>&1; do
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
            print_error "Ollama did not start in time"
        fi
        sleep 2
    done
    print_success "Ollama is ready"

    # Prüfe ob Modell bereits existiert
    if docker exec rag-ollama ollama list | grep -q "^$LLM_MODEL"; then
        print_success "Model '$LLM_MODEL' is already available"
    else
        print_warning "Model '$LLM_MODEL' not found - downloading now (this may take several minutes)..."

        # Lade Modell herunter
        if docker exec rag-ollama ollama pull "$LLM_MODEL"; then
            print_success "Model '$LLM_MODEL' downloaded successfully"
        else
            print_error "Failed to download model '$LLM_MODEL'"
        fi
    fi

    echo ""
    print_info "Available Ollama models:"
    docker exec rag-ollama ollama list
fi

echo ""
echo "========================================="
echo "  RAG System - Ready!"
echo "========================================="
echo ""
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo "  Qdrant:    http://localhost:6333/dashboard"
echo ""
print_info "Showing backend logs (Ctrl+C to exit)..."
echo ""
docker compose logs -f backend