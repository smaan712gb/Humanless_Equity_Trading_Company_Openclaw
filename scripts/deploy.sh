#!/bin/bash
# deploy.sh — Deploy Humanless Trading Operations to Tencent Lighthouse
# Usage: ./scripts/deploy.sh [paper|live]

set -euo pipefail

MODE="${1:-paper}"
echo "=== Deploying Humanless Trading Operations (${MODE} mode) ==="

# Validate environment
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
    echo "ERROR: DEEPSEEK_API_KEY not set"
    exit 1
fi

if [ "$MODE" = "live" ] && [ -z "${IBKR_LIVE_CONFIRMED:-}" ]; then
    echo "ERROR: Set IBKR_LIVE_CONFIRMED=yes to deploy in live mode"
    exit 1
fi

# Set IBKR port based on mode
if [ "$MODE" = "paper" ]; then
    IBKR_PORT=7497
    echo "Using PAPER trading (port ${IBKR_PORT})"
else
    IBKR_PORT=7496
    echo "WARNING: Using LIVE trading (port ${IBKR_PORT})"
fi

# Install Python dependencies
echo "=== Installing Python dependencies ==="
pip install ib_async qlib rdagent aiohttp

# Install Node dependencies (OpenClaw)
echo "=== Installing Node dependencies ==="
npm install

# Verify IB Gateway connection
echo "=== Verifying IB Gateway connection ==="
python3 -c "
from ib_async import IB
ib = IB()
try:
    ib.connect('127.0.0.1', ${IBKR_PORT}, clientId=99, timeout=10)
    summary = ib.accountSummary()
    equity = [s for s in summary if s.tag == 'NetLiquidation'][0].value
    print(f'Connected. Account equity: \${float(equity):,.2f}')
    ib.disconnect()
except Exception as e:
    print(f'ERROR: Cannot connect to IB Gateway on port ${IBKR_PORT}: {e}')
    exit(1)
"

# Initialize memory directories
echo "=== Initializing directories ==="
mkdir -p memory sessions data

# Validate agent configurations
echo "=== Validating agent configs ==="
for agent_dir in agents/*/; do
    if [ -d "$agent_dir" ]; then
        agent_name=$(basename "$agent_dir")
        if [ -f "${agent_dir}SOUL.md" ]; then
            echo "  OK: ${agent_name}/SOUL.md"
        else
            # Check subdirectories (trader desk has nested agents)
            for sub_dir in "${agent_dir}"*/; do
                if [ -d "$sub_dir" ] && [ -f "${sub_dir}SOUL.md" ]; then
                    sub_name=$(basename "$sub_dir")
                    echo "  OK: ${agent_name}/${sub_name}/SOUL.md"
                fi
            done
        fi
    fi
done

# Start OpenClaw Gateway
echo "=== Starting OpenClaw Gateway ==="
echo "Mode: ${MODE}"
echo "IBKR Port: ${IBKR_PORT}"
echo "DeepSeek API: configured"
echo ""
echo "Ready to start. Run: npm start"
echo "=== Deployment complete ==="
