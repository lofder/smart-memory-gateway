#!/bin/bash
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       Engram — Quick Setup           ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# 1. config.yaml
if [ ! -f config.yaml ]; then
    cp config.example.yaml config.yaml
    echo -e "${GREEN}✓${NC} Created config.yaml from template"
else
    echo -e "${YELLOW}→${NC} config.yaml already exists, skipping"
fi

# 2. .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${GREEN}✓${NC} Created .env from template"
    echo ""
    echo -e "${YELLOW}⚠ You need to edit .env and set your API key:${NC}"
    echo -e "  ${CYAN}GOOGLE_API_KEY=your-key-here${NC}"
    echo ""
else
    echo -e "${YELLOW}→${NC} .env already exists, skipping"
fi

# 3. Check for Docker vs local mode
echo ""
echo -e "${CYAN}Choose deployment mode:${NC}"
echo "  1) Docker Compose (recommended — Qdrant included)"
echo "  2) Local Python (you manage Qdrant yourself)"
echo ""
read -rp "Enter 1 or 2 [1]: " MODE
MODE=${MODE:-1}

if [ "$MODE" = "1" ]; then
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}✗ Docker not found. Install Docker first: https://docs.docker.com/get-docker/${NC}"
        exit 1
    fi

    # Patch config.yaml qdrant host for docker networking
    if grep -q "host: localhost" config.yaml; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' 's/host: localhost/host: qdrant/' config.yaml
        else
            sed -i 's/host: localhost/host: qdrant/' config.yaml
        fi
        echo -e "${GREEN}✓${NC} Updated config.yaml: qdrant host → qdrant (docker service)"
    fi

    echo ""
    echo -e "${GREEN}Setup complete! Start with:${NC}"
    echo -e "  ${CYAN}docker compose up -d${NC}"
    echo ""
    echo -e "Then add to your MCP client config (e.g. Cursor settings.json):"
    echo -e '  "engram": {'
    echo -e '    "command": "docker",'
    echo -e '    "args": ["exec", "-i", "engram-engram-1", "python", "src/server.py"]'
    echo -e '  }'

else
    # Local mode: keep localhost, install deps
    echo ""
    echo -e "${CYAN}Installing Python dependencies...${NC}"
    pip install -r requirements.txt
    echo -e "${GREEN}✓${NC} Dependencies installed"

    echo ""
    echo -e "${GREEN}Setup complete!${NC}"
    echo -e "1. Start Qdrant:  ${CYAN}./qdrant --config-path qdrant-config.yaml &${NC}"
    echo -e "   Or Docker:     ${CYAN}docker run -d -p 6333:6333 qdrant/qdrant${NC}"
    echo -e "2. Start Engram:  ${CYAN}python src/server.py${NC}"
    echo ""
    echo -e "Then add to your MCP client config:"
    echo -e '  "engram": {'
    echo -e '    "command": "python",'
    echo -e '    "args": ["'"$(pwd)"'/src/server.py"],'
    echo -e '    "env": {"GOOGLE_API_KEY": "your-key"}'
    echo -e '  }'
fi

echo ""
echo -e "${CYAN}Docs: ARCHITECTURE-v2.md | docs/usage.md${NC}"
