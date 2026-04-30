# Tim Frontiers — Support chat

Static Next.js frontend and FastAPI backend that runs an **OpenAI Agents** assistant against **OpenRouter** (chat completions) and an **MCP** server (inventory, orders, verification tools).

## Features

- Multi-turn chat with SQLite-backed sessions (`SESSION_STORE_DIR`, keyed by client UUID).
- MCP over streamable HTTP (`MCP_SERVER_URL`).
- Optional **OpenAI trace export**: set `OPENAI_API_KEY` so runs appear in the [OpenAI Traces](https://platform.openai.com/traces) dashboard while the model continues to use OpenRouter.

## Repository layout

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI app (`main.py`), `config.py`, `constants.py`, `instructions.py` |
| `frontend/` | Next.js static export (`npm run build` → `out/`) |
| `terraform/` | ECR, S3 site, optional App Runner API |
| `scripts/deploy.sh` | Terraform apply, Docker push, sync frontend to S3 |

## Environment variables

### Backend (local & App Runner)

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key for LLM calls |
| `OPENROUTER_MODEL` | No | Default `openai/gpt-4o-mini` |
| `MCP_SERVER_URL` | Yes | MCP base or full `.../mcp` URL |
| `OPENAI_API_KEY` | No | OpenAI key **only** for Agents SDK trace export (not used for chat completions when using OpenRouter) |
| `SESSION_STORE_DIR` | No | SQLite directory (default `/tmp/chat-sessions`) |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, … (default `INFO`) |

### Frontend build

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | HTTPS URL of the API (no trailing slash), e.g. App Runner URL |

Copy `.env.example` to `.env` at the repo root for local deploy scripts.

## GitHub Actions secrets

For `deploy.yml`, configure:

| Secret | Purpose |
|--------|---------|
| `AWS_ROLE_ARN` | OIDC role for AWS |
| `OPENROUTER_API_KEY` | OpenRouter |
| `MCP_SERVER_URL` | MCP server URL |
| `OPENAI_API_KEY` | Optional; enables trace export in production |
| `TF_STATE_BUCKET` / `TF_STATE_REGION` | Remote Terraform state (if used) |

## Local quickstart

```bash
cd backend
pip install -r requirements.txt
export OPENROUTER_API_KEY=…
export MCP_SERVER_URL=…
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd frontend
npm ci
export NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
npm run build
```

## Deploy

```bash
./scripts/deploy.sh dev
```

Requires AWS CLI, Terraform, Docker, and Node. See `terraform/` variables for `openrouter_*`, `mcp_server_url`, and optional `openai_api_key`.

## License

Use per your assessment or organization policy.
