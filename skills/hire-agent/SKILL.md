---
name: hire-agent
description: CEO skill to dynamically create and deploy new specialist agents at runtime
user-invocable: false
metadata:
  openclaw:
    requires:
      bins: []
      env: []
---

# Hire Agent Skill — CEO's Ability to Spawn Specialist Agents

## Description
Allows the CEO to dynamically create, configure, and deploy new specialist agents
at runtime. The CEO identifies a capability gap, defines the role, and the system
creates the agent's workspace (SOUL.md, AGENTS.md, MEMORY.md), registers it on the
message bus, and assigns it to the appropriate team.

## Authorized Agents
- CEO (only — hiring authority)

## How It Works

### 1. CEO Identifies a Need
The CEO's reasoning engine detects a gap:
- "We're missing sector rotation signals — need a Sector Trend Watcher"
- "Unusual volume on LITE but no one is tracking order flow"
- "Earnings season starting — need dedicated earnings coverage"

### 2. CEO Defines the Role
```json
{
  "agent_name": "sector_trend_watcher",
  "display_name": "Sector Trend Watcher",
  "model": "deepseek-chat",
  "team": "specialist",
  "reports_to": "ceo",
  "purpose": "Monitor sector rotation, track relative strength, alert on regime changes",
  "tools": ["news-sentiment", "market-calendar"],
  "heartbeat_seconds": 300,
  "auto_start": true
}
```

### 3. System Creates Agent Workspace
- Creates `agents/specialist/{agent_name}/SOUL.md`
- Creates `agents/specialist/{agent_name}/AGENTS.md`
- Creates `agents/specialist/{agent_name}/MEMORY.md`
- Registers on message bus
- Starts monitoring loop

### 4. CEO Can Fire/Pause Agents
- **Pause**: Stop the agent's heartbeat but preserve memory
- **Fire**: Stop the agent and archive its workspace
- **Reassign**: Change reporting line or tool access

## Constraints
- Maximum 10 specialist agents active at any time
- Each specialist must have a clear, non-overlapping purpose
- Specialists cannot place orders — they report to Scout/Analyst/Strategist
- CEO must approve every new hire (no self-spawning chains)
