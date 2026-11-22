#!/usr/bin/env bash
# Start FamilyOS: Neo4j (Docker) + FastAPI context engine on :8000 + Next.js dashboard on :3000.
# Claude key: read from $ANTHROPIC_API_KEY, else ~/Desktop/claude.env (override with FAMILYOS_KEY_FILE).
# Optional: FINANCIAL_ENGINE_MCP_URL=http://host:port/mcp (or FINANCIAL_ENGINE_MCP_COMMAND="...") to fetch families over MCP;
#           FINANCIAL_ENGINE_URL=... to pull live data over HTTP; FAMILYOS_HOST=0.0.0.0 so a colleague on the LAN can push; FAMILYOS_NEO4J=0 to run without Neo4j.
set -e
cd "$(dirname "$0")"

if [ "${FAMILYOS_NEO4J:-1}" != "0" ] && command -v docker >/dev/null; then
  docker info >/dev/null 2>&1 || { echo "Starting Colima…"; colima start --cpu 2 --memory 4 >/dev/null; }
  if docker ps -a --format '{{.Names}}' | grep -qx familyos-neo4j; then
    docker start familyos-neo4j >/dev/null
  else
    docker run -d --name familyos-neo4j -p 127.0.0.1:7474:7474 -p 127.0.0.1:7687:7687 \
      -e NEO4J_AUTH=neo4j/familyos-demo -e NEO4J_server_memory_heap_max__size=1G neo4j:5-community >/dev/null
  fi
  echo -n "Waiting for Neo4j"; for _ in $(seq 1 40); do curl -s -o /dev/null localhost:7474 && break; echo -n "."; sleep 2; done; echo " ready (browser: http://localhost:7474, neo4j / familyos-demo)"
fi

trap 'kill 0' EXIT
(cd backend && .venv/bin/uvicorn app.main:app --host "${FAMILYOS_HOST:-127.0.0.1}" --port 8000 --reload) &
(cd frontend && npx next dev -p 3000) &
sleep 6 && curl -s -X POST localhost:8000/api/family/F001/graph/sync >/dev/null || true
wait
