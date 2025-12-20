# Cerina

An AI-powered multi-agent system for generating clinical CBT exercises through collaborative agent workflows with human-in-the-loop approval gates.

**🌐 [Try it live →](https://cerina-v0.vercel.app/)**

## Features

- **Multi-Agent Architecture**: 6 specialized agents (Router, Planner, Draftsman, Critic, Reviser, Synthesizer) orchestrated via LangGraph
- **Checkpoint System**: Persistent state management with PostgresSaver for workflow resumption across server restarts
- **Human-in-the-Loop**: Approval gates at critical decision points with seamless workflow pause/resume
- **Iterative Refinement**: Critique-revision loops ensure quality through multi-perspective evaluation
- **Real-time Streaming**: WebSocket-based event streaming for live agent activity visualization

## Tech Stack

**Backend:**
- Python, FastAPI, LangGraph, LangChain
- PostgreSQL (with PostgresSaver for checkpointing)
- Google Gemini API

**Frontend:**
- React, TypeScript, Vite
- Tailwind CSS, Framer Motion
- Firebase Authentication
- WebSocket for real-time updates

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
# Set up environment variables (see .env.example)
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Architecture

The system follows a pipeline workflow:
```
Router → Planner → [HITL Approval] → Draftsman → Critic ⟷ Reviser (loop) → Synthesizer
```

Each agent is implemented as a LangGraph subgraph with structured outputs and event emission for real-time visibility.

