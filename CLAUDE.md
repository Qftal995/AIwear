# AIWear 2.0 Project

## Permissions
- All file edits, writes, and deletes within this project are pre-approved
- All shell commands (PowerShell, git, mvn, npm, python) are pre-approved
- D:\Agent\ and all subdirectories are trusted workspace
- D:\obsidian\笔记\AIWear2.0\ is trusted workspace for documentation

## Environment
- Python 3.14 at C:\Users\86130\AppData\Local\Programs\Python\Python314\python.exe
- Java 17+ with Maven wrapper in apps/api-java
- Node.js with npm in apps/web
- PowerShell 5.1 as default shell
- .env file at D:\Agent\.env for API keys

## Code Conventions
- No emoji, no docstrings, no AI-flavored comments
- Python: absolute imports, no shebang
- Frontend: preserve existing CSS variables and purple gradient design system
- Java: follow existing Result<T> pattern, Spring Boot conventions
- Names as documentation — well-named identifiers over comments

## Architecture
- apps/ai-service: Python Flask :5000 — agent orchestration, tools, FAISS vector search
- apps/api-java: Spring Boot :8081 — user auth, file management, proxy to Python
- apps/web: Vue 3 + Vite :5173 — 8 page SPA
- data/: FAISS index + uploads (runtime data)
- deploy/: Docker Compose for MySQL + Redis + Nginx
