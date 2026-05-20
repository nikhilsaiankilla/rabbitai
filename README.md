# 🐇 RabbitAI — AI Code Reviewer

> Open-source AI code reviewer that auto-reviews GitHub PRs with zero cost and full self-hosting.

**LangGraph agents · Knowledge graph blast-radius detection · mem0 persistent memory · MCP server for Claude/Cursor**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-agent-purple.svg)](https://langchain-ai.github.io/langgraph)
[![Gemini](https://img.shields.io/badge/Gemini-free%20tier-orange.svg)](https://aistudio.google.com)

---

## What is RabbitAI?

RabbitAI is an open-source AI code reviewer that automatically reviews your GitHub pull requests and posts structured comments — bugs, security issues, performance problems, and improvement suggestions.

Unlike other code reviewers, RabbitAI:
- Builds a **knowledge graph** of your codebase to detect blast-radius of changes
- Uses **mem0 persistent memory** to get smarter with every PR it reviews
- Runs **completely free** using Gemini free tier and local ChromaDB
- Works as a **GitHub Action**, a **FastAPI server**, or an **MCP server** inside Claude/Cursor

---

## Demo

```
🤖 RabbitAI Code Review

📊 Score: 7/10 · 3 issues found

🔴 Bug
→ auth.ts line 23: user.id can be undefined if session expires before check

🟠 Security
→ db.ts line 45: query is not parameterized — SQL injection risk

🟡 Performance
→ dashboard.tsx line 89: value recalculated on every render, consider useMemo

🟢 Looks good
→ Error boundaries correctly implemented
→ TypeScript types well-defined throughout

🧠 Memory insight
→ db.ts has 12 dependents in this codebase — this change is marked high risk

---
Powered by RabbitAI · rabbitai.nikhilsai.in · MIT License
```

---

## Features

- **7-node LangGraph workflow** — fetch, graph, embed, classify, retrieve, review, post
- **NetworkX knowledge graph** — maps file dependencies, detects high-risk changes by blast radius
- **RAG pipeline** — chunks PR diff, embeds via Gemini, stores in local ChromaDB, retrieves relevant context
- **mem0 persistent memory** — remembers repo conventions, past issues, and codebase patterns across PRs
- **Change type routing** — classifies each PR as bug fix, feature, refactor, or security and adjusts review focus
- **MCP server** — use RabbitAI directly inside Claude or Cursor IDE without GitHub Action
- **Zero cost** — Gemini free tier + local ChromaDB + open-source mem0
- **Fully self-hostable** — no cloud dependency, runs entirely on your machine

---

## How It Works

```
PR opened
→ Fetch diff via GitHub API
→ Build NetworkX file dependency graph
→ Chunk diff → Gemini embeddings → ChromaDB
→ Classify change type (bug fix / feature / refactor / security)
→ Load repo memory from mem0
→ Retrieve relevant chunks
→ Gemini reviews with full context + memory + graph insights
→ Post structured comment on PR
→ Save new learnings to mem0
```

---

## Free Stack

| Layer | Tool | Cost |
|---|---|---|
| LLM | Gemini 2.0 Flash | Free tier |
| Embeddings | Gemini Embedding | Free tier |
| Memory | mem0 (local) | Free |
| Knowledge graph | NetworkX | Free |
| Vector store | ChromaDB (local) | Free |
| MCP | Anthropic MCP SDK | Free |
| GitHub integration | PyGithub | Free |
| **Total** | | **$0/month** |

---

## Quick Start

### Option 1 — GitHub Action (recommended)

Add this to `.github/workflows/review.yml` in your repo:

```yaml
on: [pull_request]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: RabbitAI Code Review
        uses: nikhilsaiankilla/rabbitai@v1
        with:
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

Add `GEMINI_API_KEY` to your repo secrets. Get one free at [aistudio.google.com](https://aistudio.google.com).

Done. Open a PR and RabbitAI reviews it automatically.

---

### Option 2 — MCP Server (Claude / Cursor)

```bash
git clone https://github.com/nikhilsaiankilla/rabbitai
cd rabbitai
pip install -r requirements.txt
cp config.example.yaml config.yaml
# fill in your config.yaml
python mcp/server.py
```

Add to your Claude or Cursor MCP config:
```json
{
  "mcpServers": {
    "rabbitai": {
      "command": "python",
      "args": ["mcp/server.py"]
    }
  }
}
```

Now type "review my current PR" directly inside your IDE.

---

### Option 3 — Self-host FastAPI

```bash
git clone https://github.com/nikhilsaiankilla/rabbitai
cd rabbitai
pip install -r requirements.txt
cp config.example.yaml config.yaml
# fill in your config.yaml
uvicorn agent:app --reload
```

---

## Configuration

Copy `config.example.yaml` to `config.yaml` and fill in:

```yaml
github_token: "ghp_xxx"              # github.com → Settings → Developer settings → PAT
gemini_api_key: "xxx"                # free at aistudio.google.com

review:
  language: "typescript"             # primary language of your repo
  focus:
    - bugs
    - security
    - performance
  min_risk_score: 6                  # only post comment if score below this
  post_score: true                   # show 1-10 score in PR comment

memory:
  enabled: true
  repo_context: |
    Describe your repo here so RabbitAI understands context from day one.
    Example: This repo uses Next.js 15, Drizzle ORM, TypeScript strict mode.
    Prefer functional components. No class components.
```

---

## Project Structure

```
rabbitai/
├── .github/
│   └── workflows/
│       └── review.yml          ← GitHub Action trigger
├── nodes/
│   ├── fetcher.py              ← GitHub API, fetch PR diff
│   ├── graph_builder.py        ← NetworkX file dependency graph
│   ├── embedder.py             ← Gemini embeddings + ChromaDB
│   ├── classifier.py           ← change type detection
│   ├── retriever.py            ← ChromaDB semantic search
│   ├── reviewer.py             ← Gemini review generation
│   └── poster.py               ← GitHub PR comment poster
├── memory/
│   └── repo_memory.py          ← mem0 persistent repo context
├── mcp/
│   └── server.py               ← MCP server for IDE integration
├── utils/
│   ├── config.py               ← config.yaml loader
│   └── prompts.py              ← all review prompts
├── agent.py                    ← LangGraph workflow entry point
├── config.example.yaml         ← copy to config.yaml and fill in
├── requirements.txt
└── README.md
```

---

## Roadmap

- [x] LangGraph 7-node workflow
- [x] NetworkX knowledge graph
- [x] ChromaDB RAG pipeline
- [x] mem0 persistent memory
- [x] MCP server
- [ ] Support for GitLab and Bitbucket
- [ ] Web dashboard for review history
- [ ] Slack and Discord notifications
- [ ] Fine-tuned review prompts per language

---

## Contributing

PRs welcome. RabbitAI reviews its own PRs. 🐇

1. Fork the repo
2. Create your branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'feat: your feature'`)
4. Push and open a PR

---

## License

MIT — use it, fork it, self-host it, build on it.

---

## Built by

**Nikhil Sai** · [@nikhilbuildss](https://x.com/itzznikhilsai) · [nikhilsai.in](https://nikhilsai.in)

If this helped you, star the repo ⭐ and share it on X.
