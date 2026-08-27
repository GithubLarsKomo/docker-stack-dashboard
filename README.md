# AI Stack Ops Dashboard v5

v5 trennt klassische Services und MCP-Server sauber.

## Neu in v5

- `Services`-Tab enthält nur klassische APIs/Infrastruktur.
- `MCP`-Tab enthält ausschließlich MCP-Server.
- MCP-spezifische Erkennung: `/sse`, `/mcp`, `POST /mcp`, `OPTIONS /mcp`, `/message`.
- HTTP 401/403/405/426 wird bei MCP als erreichbar interpretiert, aber mit Methode/Auth/Handshake-Hinweis.
- Service-/MCP-spezifische Prompt-Erzeugung.
- Prompts sind auf Fehlerabstellung, Endpoint-Findung und Health-Endpoint-Erzeugung optimiert.
- Vorbereitung auf späteren SSH-Agent/Cron-Betrieb ohne aktive SSH-Ausführung.

## Installation

```bash
cd ~/docker-compose
rm -rf docker-stack-dashboard
mkdir docker-stack-dashboard
cd docker-stack-dashboard
unzip docker-stack-ops-dashboard-v5.zip
docker compose up -d --build
```

Öffnen:

```text
http://localhost:8088
```

## Sicherheit

Das Dashboard mountet den Docker-Socket. Nur lokal/Admin-Netz verwenden.
Für spätere Agent-Automation: separater SSH-Key, Allowlist, Dry-Run, Audit-Log, Rollback, keine blind-autonomen destructive commands.
