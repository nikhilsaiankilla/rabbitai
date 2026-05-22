<p align="center">
  <img src="./assets/banner.png" alt="RabbitAI Logo" width="100%" />
</p>

# RabbitAI — AI Code Reviewer

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
- Works as a **GitHub Action** or an **MCP server** inside Claude/Cursor

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
Powered by RabbitAI · MIT License
```

---

## Features

- **9-node LangGraph workflow** — fetch, graph, classify, embed, retrieve, load_memory, review, post, save_memory
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
→ Fetch diff + metadata via GitHub API
→ Build NetworkX file dependency graph (blast radius detection)
→ Classify change type (bug fix / feature / refactor / security)
→ Chunk diff → Gemini embeddings → ChromaDB
→ Load repo memory from mem0 (past learnings)
→ Retrieve relevant chunks via semantic search
→ Gemini reviews with full context + memory + graph insights
→ Post structured comment on PR
→ Save new learnings to mem0
```

---

## Free Stack

| Layer | Tool | Cost |
|---|---|---|
| LLM | Gemini 2.0 Flash | Free tier |
| Embeddings | Gemini text-embedding-004 | Free tier |
| Memory | mem0 (local) | Free |
| Knowledge graph | NetworkX | Free |
| Vector store | ChromaDB (local) | Free |
| MCP | Anthropic MCP SDK | Free |
| GitHub integration | PyGithub | Free |
| **Total** | | **$0/month** |

---

## Quick Start

### Option 1 — GitHub Action (recommended)

**1. Add the workflow file** to your repo at `.github/workflows/review.yml`:

```yaml
name: RabbitAI Code Review

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      contents: read
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run RabbitAI
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: |
          python -c "
          import os
          from agent import run
          result = run(os.environ['GITHUB_REPOSITORY'], int(os.environ['PR_NUMBER']))
          print(result.comment_url if result.posted else result.reason)
          "
```

**2. Add your Gemini API key** to repo secrets:
`Settings → Secrets and variables → Actions → New repository secret`
Name: `GEMINI_API_KEY` — get one free at [aistudio.google.com](https://aistudio.google.com)

`GITHUB_TOKEN` is injected automatically by GitHub — you don't touch it.

**3. Open a PR.** RabbitAI reviews it automatically.

---

### Option 2 — MCP Server (Claude / Cursor)

Run RabbitAI locally and trigger reviews directly from Claude or Cursor.

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
      "args": ["path/to/rabbitai/mcp/server.py"]
    }
  }
}
```

Then type inside Claude or Cursor:
> "Review PR #12 in nikhilsaiankilla/myrepo"

---

## Local Testing

```bash
git clone https://github.com/nikhilsaiankilla/rabbitai
cd rabbitai
pip install -r requirements.txt
cp config.example.yaml config.yaml
# fill in gemini_api_key and github_token in config.yaml
```

Create a `test.py`:

```python
from agent import run

result = run(
    repo_name="your-username/your-repo",
    pr_number=1,
)
print(result)
```

```bash
python test.py
```

If it works, you'll see the review printed in terminal and a comment posted on the PR.

---

## Configuration

Copy `config.example.yaml` to `config.yaml` and fill in:

```yaml
github_token: "ghp_xxx"         # only needed for local dev
gemini_api_key: "xxx"           # free at aistudio.google.com

vector_store:
  provider: "chromadb"          # chromadb | pinecone | qdrant
  path: "./chroma_db"           # chromadb only — local folder
  collection: "pr-chunks"

memory:
  enabled: true
  repo_context: |
    Describe your repo so RabbitAI has context from day one.
    Example: Next.js 15, Drizzle ORM, TypeScript strict mode.
    Prefer functional components. No class components.

review:
  language: "typescript"        # primary language of your repo
  focus:
    - bugs
    - security
    - performance
  min_risk_score: 6             # skip comment if score is above this
  post_score: true              # show 1-10 score in PR comment
```

---

## Project Structure

```
rabbitai/
├── .github/
│   └── workflows/
│       └── review.yml          ← GitHub Action trigger
├── nodes/
│   ├── fetcher.py              ← GitHub API, fetch PR diff + metadata
│   ├── graph_builder.py        ← NetworkX file dependency graph + blast radius
│   ├── classifier.py           ← change type detection (bug/feature/security/refactor)
│   ├── embedder.py             ← Gemini embeddings + ChromaDB storage
│   ├── retriever.py            ← semantic search over stored chunks
│   ├── reviewer.py             ← Gemini review generation
│   └── poster.py               ← GitHub PR comment poster
├── memory/
│   └── repo_memory.py          ← mem0 persistent repo context
├── mcp/
│   └── server.py               ← MCP server for Claude/Cursor
├── utils/
│   ├── config.py               ← config.yaml loader with env var overrides
│   └── prompts.py              ← review prompt templates
├── agent.py                    ← LangGraph 9-node workflow
├── config.example.yaml         ← copy to config.yaml and fill in
├── requirements.txt
└── README.md
```

---

## Roadmap

- [x] LangGraph 9-node workflow
- [x] NetworkX knowledge graph + blast radius detection
- [x] ChromaDB RAG pipeline
- [x] mem0 persistent memory
- [x] MCP server for Claude/Cursor
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

**Nikhil Sai** · [@itzznikhilsai](https://x.com/itzznikhilsai) · [nikhilsai.in](https://nikhilsai.in)

If this helped you, star the repo ⭐ and share it on X.