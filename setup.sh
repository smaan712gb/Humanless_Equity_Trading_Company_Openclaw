#!/bin/bash
# setup.sh — One-command deployment of Humanless Equity Trading Company
# Installs Paperclip + OpenClaw, deploys agents, skills, and connects everything.
#
# Usage: ./setup.sh [--skip-install]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCLAW_HOME="${HOME}/.openclaw"
PAPERCLIP_HOME="${HOME}/.paperclip"
SKIP_INSTALL="${1:-}"

echo "=============================================="
echo " Humanless Equity Trading Company — Setup"
echo "=============================================="
echo ""

# ── Step 0: Check prerequisites ──
echo "[0/7] Checking prerequisites..."

command -v node >/dev/null 2>&1 || { echo "ERROR: Node.js required. Install from https://nodejs.org"; exit 1; }
command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || { echo "ERROR: Python 3.10+ required"; exit 1; }

NODE_VERSION=$(node -v | cut -d. -f1 | tr -d 'v')
if [ "$NODE_VERSION" -lt 20 ]; then
    echo "WARNING: Node.js 20+ recommended. You have $(node -v)"
fi

if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
    if [ -f "$SCRIPT_DIR/.env" ]; then
        export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
    fi
fi

if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
    echo "ERROR: DEEPSEEK_API_KEY not set. Edit .env first."
    exit 1
fi

echo "  Node.js: $(node -v)"
echo "  Python: $(python3 --version 2>/dev/null || python --version)"
echo "  DeepSeek API key: set"
echo ""

# ── Step 1: Install Paperclip ──
if [ "$SKIP_INSTALL" != "--skip-install" ]; then
    echo "[1/7] Installing Paperclip..."
    npm install -g paperclipai@latest 2>/dev/null || npx paperclipai --version
    echo "  Paperclip installed."
    echo ""

    # ── Step 2: Install OpenClaw ──
    echo "[2/7] Installing OpenClaw..."
    npm install -g openclaw@latest 2>/dev/null || echo "  OpenClaw may need manual install"
    echo "  OpenClaw installed."
    echo ""
else
    echo "[1-2/7] Skipping install (--skip-install flag)"
    echo ""
fi

# ── Step 3: Install Python dependencies ──
echo "[3/7] Installing Python dependencies..."
pip install ib_async openai pydantic pyyaml python-dotenv aiosqlite 2>/dev/null || pip3 install ib_async openai pydantic pyyaml python-dotenv aiosqlite
echo ""

# ── Step 4: Deploy OpenClaw configuration ──
echo "[4/7] Deploying OpenClaw configuration..."
mkdir -p "$OPENCLAW_HOME"
cp "$SCRIPT_DIR/openclaw.json" "$OPENCLAW_HOME/openclaw.json"
echo "  Config deployed to $OPENCLAW_HOME/openclaw.json"
echo ""

# ── Step 5: Deploy agent workspaces ──
echo "[5/7] Deploying agent workspaces..."

deploy_workspace() {
    local src="$1"
    local agent_id="$2"
    local target="$OPENCLAW_HOME/workspaces/$agent_id"
    mkdir -p "$target"
    cp "$src"/*.md "$target/" 2>/dev/null || true
    # Create skills symlink
    mkdir -p "$target/skills"
    for skill_dir in "$SCRIPT_DIR/skills"/*/; do
        local skill_name=$(basename "$skill_dir")
        if [ ! -L "$target/skills/$skill_name" ]; then
            ln -sf "$skill_dir" "$target/skills/$skill_name" 2>/dev/null || cp -r "$skill_dir" "$target/skills/$skill_name"
        fi
    done
    echo "  Deployed: $agent_id"
}

# Core team
for agent in ceo scout analyst strategist executor position-manager compliance auditor; do
    deploy_workspace "$SCRIPT_DIR/workspaces/$agent" "$agent"
done

# Specialist team
for agent in sector-trend-watcher volume-flow-analyst twitter-sentiment futures-index-watcher earnings-calendar options-flow-scanner technical-analyst short-interest-tracker; do
    deploy_workspace "$SCRIPT_DIR/workspaces/specialist/$agent" "$agent"
done

# Deploy Python tools to each workspace that needs IBKR access
for agent in executor position-manager strategist volume-flow-analyst futures-index-watcher options-flow-scanner technical-analyst; do
    target="$OPENCLAW_HOME/workspaces/$agent/tools"
    mkdir -p "$target"
    cp "$SCRIPT_DIR/tools/"*.py "$target/" 2>/dev/null || true
done

echo ""

# ── Step 6: Set up Paperclip company ──
echo "[6/7] Setting up Paperclip company..."
if command -v paperclipai >/dev/null 2>&1; then
    echo "  Importing company package..."
    paperclipai company import "$SCRIPT_DIR" --target new 2>/dev/null || echo "  (Import will complete via Paperclip UI)"
else
    echo "  Run 'npx paperclipai onboard --yes' then import this directory as a company"
fi
echo ""

# ── Step 7: Verify ──
echo "[7/7] Verifying deployment..."
echo ""

# Check workspaces
AGENT_COUNT=0
for ws in "$OPENCLAW_HOME/workspaces"/*/; do
    if [ -f "$ws/SOUL.md" ]; then
        AGENT_COUNT=$((AGENT_COUNT + 1))
    fi
done
echo "  Agent workspaces deployed: $AGENT_COUNT"

# Check skills
SKILL_COUNT=0
for sk in "$SCRIPT_DIR/skills"/*/SKILL.md; do
    SKILL_COUNT=$((SKILL_COUNT + 1))
done
echo "  Skills available: $SKILL_COUNT"

# Check tools
echo "  Python tools: $(ls "$SCRIPT_DIR/tools/"*.py 2>/dev/null | wc -l)"

echo ""
echo "=============================================="
echo " Setup complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Start Paperclip:  npx paperclipai run"
echo "  2. Start OpenClaw:   openclaw gateway start"
echo "  3. Connect them:     In Paperclip UI > Company Settings > Generate OpenClaw Invite"
echo "  4. Start IB Gateway: Port ${IBKR_PORT:-4002}, Trusted IP 127.0.0.1"
echo "  5. Verify IBKR:      python3 $SCRIPT_DIR/scripts/ibkr_diagnostic.py"
echo ""
echo "The system will auto-detect market sessions and begin trading."
echo "Today's session: $(python3 -c 'from tools.market_calendar import get_session_info; import json; print(json.dumps(get_session_info(), indent=2))' 2>/dev/null || echo 'Run from project root to check')"
