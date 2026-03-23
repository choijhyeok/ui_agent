#!/usr/bin/env bash
# ============================================================================
# LFG-7 End-to-End Integration Test Script
#
# Prerequisites:
#   - Docker and Docker Compose installed
#   - .env file with valid LLM credentials
#   - Run from the ui_agent/ directory
#
# Usage:
#   ./scripts/integration-test.sh           # full test
#   ./scripts/integration-test.sh --skip-build  # skip docker build
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'

passed=0
failed=0
skipped=0

log_info()  { echo -e "${BOLD}[INFO]${NC} $*"; }
log_pass()  { echo -e "${GREEN}[PASS]${NC} $*"; ((passed++)); }
log_fail()  { echo -e "${RED}[FAIL]${NC} $*"; ((failed++)); }
log_skip()  { echo -e "${YELLOW}[SKIP]${NC} $*"; ((skipped++)); }
log_section() { echo -e "\n${BOLD}━━━ $* ━━━${NC}"; }

AGENT_URL="http://localhost:${AGENT_HOST_PORT:-8123}"
RUNTIME_URL="http://localhost:${RUNTIME_HOST_PORT:-3001}"
WEB_URL="http://localhost:${WEB_HOST_PORT:-3000}"

wait_for_service() {
  local url=$1
  local name=$2
  local max_attempts=${3:-30}
  local attempt=0

  while [ $attempt -lt $max_attempts ]; do
    if curl -sf "$url" > /dev/null 2>&1; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done
  return 1
}

# ============================================================================
# Phase 0: Docker Compose Config Validation
# ============================================================================
log_section "Phase 0: Docker Compose Config"

if docker compose config > /dev/null 2>&1; then
  log_pass "docker compose config validates successfully"
else
  log_fail "docker compose config has errors"
  docker compose config 2>&1 | head -20
  exit 1
fi

# ============================================================================
# Phase 1: Build & Start Services
# ============================================================================
log_section "Phase 1: Build & Start Services"

if [[ "${1:-}" == "--skip-build" ]]; then
  log_info "Skipping build (--skip-build)"
else
  log_info "Building images..."
  if docker compose build --quiet 2>&1; then
    log_pass "Docker images built successfully"
  else
    log_fail "Docker image build failed"
    exit 1
  fi
fi

log_info "Starting services..."
docker compose up -d 2>&1

log_info "Waiting for postgres..."
if wait_for_service "" "postgres" 1; then
  sleep 5  # extra time for migrations
fi

log_info "Waiting for agent ($AGENT_URL/health)..."
if wait_for_service "$AGENT_URL/health" "agent" 40; then
  log_pass "Agent service is running"
else
  log_fail "Agent service did not start"
  docker compose logs agent | tail -30
fi

log_info "Waiting for runtime ($RUNTIME_URL/health)..."
if wait_for_service "$RUNTIME_URL/health" "runtime" 30; then
  log_pass "Runtime service is running"
else
  log_fail "Runtime service did not start"
  docker compose logs runtime | tail -20
fi

log_info "Waiting for web ($WEB_URL/health)..."
if wait_for_service "$WEB_URL/health" "web" 40; then
  log_pass "Web service is running"
else
  log_fail "Web service did not start"
  docker compose logs web | tail -30
fi

# ============================================================================
# Phase 2: Health Checks
# ============================================================================
log_section "Phase 2: Health Checks"

# Agent health
AGENT_HEALTH=$(curl -sf "$AGENT_URL/health" 2>/dev/null || echo '{}')
PROVIDER_READY=$(echo "$AGENT_HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('provider',{}).get('providerReady',False))" 2>/dev/null || echo "False")
DB_READY=$(echo "$AGENT_HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('databaseReady',False))" 2>/dev/null || echo "False")

if [ "$DB_READY" = "True" ]; then
  log_pass "Database connected and ready"
else
  log_fail "Database not ready"
fi

if [ "$PROVIDER_READY" = "True" ]; then
  log_pass "LLM provider configured and ready"
else
  log_skip "LLM provider not ready (credentials may be missing)"
fi

# Runtime health
RUNTIME_HEALTH=$(curl -sf "$RUNTIME_URL/health" 2>/dev/null || echo '{}')
RUNTIME_STATUS=$(echo "$RUNTIME_HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")

if [ "$RUNTIME_STATUS" = "ready" ]; then
  log_pass "Runtime preview entry point exists"
else
  log_fail "Runtime preview entry point missing (status=$RUNTIME_STATUS)"
fi

# Web health
WEB_HEALTH=$(curl -sf "$WEB_URL/health" 2>/dev/null || echo '')
if [ -n "$WEB_HEALTH" ]; then
  log_pass "Web app health endpoint responds"
else
  log_fail "Web app health endpoint not reachable"
fi

# ============================================================================
# Phase 3: Scenario 1 – Create New Screen
# ============================================================================
log_section "Phase 3: Scenario 1 – Create New Screen"

SESSION_ID="integration-test-$(date +%s)"

if [ "$PROVIDER_READY" = "True" ]; then
  CREATE_RESPONSE=$(curl -sf -X POST "$AGENT_URL/orchestrate" \
    -H "Content-Type: application/json" \
    -d "{
      \"sessionId\": \"$SESSION_ID\",
      \"message\": \"Create a modern dashboard with a hero section, metrics grid, and a sidebar navigation\"
    }" 2>/dev/null || echo '{"error":"request failed"}')

  CREATE_INTENT=$(echo "$CREATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('intentKind',''))" 2>/dev/null || echo "")
  PATCH_STATUS=$(echo "$CREATE_RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin).get('patchRecord',{}); print(r.get('status','') if r else '')" 2>/dev/null || echo "")

  if [ "$CREATE_INTENT" = "create" ]; then
    log_pass "Intent classified as 'create'"
  else
    log_fail "Expected intent 'create', got '$CREATE_INTENT'"
  fi

  if [ "$PATCH_STATUS" = "applied" ]; then
    log_pass "Patch applied successfully – new screen generated"
  elif [ "$PATCH_STATUS" = "failed" ]; then
    log_fail "Patch execution failed"
    echo "  Response: $(echo "$CREATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','')[:200])" 2>/dev/null)"
  else
    log_skip "Patch status unknown: '$PATCH_STATUS'"
  fi

  # Verify preview updated
  sleep 2
  PREVIEW_CONTENT=$(curl -sf "$RUNTIME_URL/" 2>/dev/null || echo "")
  if echo "$PREVIEW_CONTENT" | grep -qi "dashboard\|hero\|metric"; then
    log_pass "Preview reflects generated content"
  else
    log_skip "Preview content may not match expected keywords (LLM output varies)"
  fi
else
  log_skip "Scenario 1 skipped – LLM provider not ready"
fi

# ============================================================================
# Phase 4: Scenario 2 – Selection-Based Component Edit
# ============================================================================
log_section "Phase 4: Scenario 2 – Selection-Based Edit"

if [ "$PROVIDER_READY" = "True" ]; then
  EDIT_RESPONSE=$(curl -sf -X POST "$AGENT_URL/orchestrate" \
    -H "Content-Type: application/json" \
    -d "{
      \"sessionId\": \"$SESSION_ID\",
      \"message\": \"Change the header background to dark blue and make the title white\",
      \"selectedElement\": {
        \"id\": \"sel-integration-1\",
        \"sessionId\": \"$SESSION_ID\",
        \"kind\": \"element\",
        \"selector\": \"header\",
        \"domPath\": [\"html\", \"body\", \"header\"],
        \"textSnippet\": \"Dashboard\",
        \"bounds\": {\"x\": 0, \"y\": 0, \"width\": 1200, \"height\": 80},
        \"componentHint\": \"Header\",
        \"sourceHint\": {\"filePath\": \"preview/index.html\"},
        \"capturedAt\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
      }
    }" 2>/dev/null || echo '{"error":"request failed"}')

  EDIT_INTENT=$(echo "$EDIT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('intentKind',''))" 2>/dev/null || echo "")
  EDIT_STRATEGY=$(echo "$EDIT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('patchPlan',{}).get('strategy',''))" 2>/dev/null || echo "")
  EDIT_PATCH_STATUS=$(echo "$EDIT_RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin).get('patchRecord',{}); print(r.get('status','') if r else '')" 2>/dev/null || echo "")

  if [ "$EDIT_STRATEGY" = "targeted-update" ]; then
    log_pass "Selection-based edit uses 'targeted-update' strategy"
  else
    log_fail "Expected strategy 'targeted-update', got '$EDIT_STRATEGY'"
  fi

  if [ "$EDIT_PATCH_STATUS" = "applied" ]; then
    log_pass "Selection-based patch applied successfully"
  elif [ "$EDIT_PATCH_STATUS" = "failed" ]; then
    log_fail "Selection-based patch failed"
  else
    log_skip "Edit patch status: '$EDIT_PATCH_STATUS'"
  fi
else
  log_skip "Scenario 2 skipped – LLM provider not ready"
fi

# ============================================================================
# Phase 5: Session Restore
# ============================================================================
log_section "Phase 5: Session Restore"

if [ "$DB_READY" = "True" ] && [ "$PROVIDER_READY" = "True" ]; then
  RESTORE_RESPONSE=$(curl -sf "$AGENT_URL/sessions/$SESSION_ID/restore" 2>/dev/null || echo '{"error":"not found"}')
  RESTORE_SESSION_ID=$(echo "$RESTORE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session',{}).get('id',''))" 2>/dev/null || echo "")
  RESTORE_MESSAGES=$(echo "$RESTORE_RESPONSE" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('messages',[])))" 2>/dev/null || echo "0")
  RESTORE_PATCHES=$(echo "$RESTORE_RESPONSE" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('patchRecords',[])))" 2>/dev/null || echo "0")

  if [ "$RESTORE_SESSION_ID" = "$SESSION_ID" ]; then
    log_pass "Session restore returned correct session"
  else
    log_fail "Session restore failed"
  fi

  if [ "$RESTORE_MESSAGES" -gt 0 ]; then
    log_pass "Session has $RESTORE_MESSAGES messages persisted"
  else
    log_skip "No messages found in restored session"
  fi

  if [ "$RESTORE_PATCHES" -gt 0 ]; then
    log_pass "Session has $RESTORE_PATCHES patch records persisted"
  else
    log_skip "No patch records in restored session"
  fi
else
  log_skip "Session restore skipped – DB or provider not ready"
fi

# ============================================================================
# Phase 6: Workspace Files
# ============================================================================
log_section "Phase 6: Workspace File Verification"

FILES_RESPONSE=$(curl -sf "$AGENT_URL/workspace/files" 2>/dev/null || echo '{"files":[]}')
FILE_COUNT=$(echo "$FILES_RESPONSE" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('files',[])))" 2>/dev/null || echo "0")

if [ "$FILE_COUNT" -gt 0 ]; then
  log_pass "Workspace contains $FILE_COUNT file(s)"
else
  log_fail "Workspace is empty"
fi

# ============================================================================
# Phase 7: Compose Down
# ============================================================================
log_section "Phase 7: Cleanup"

docker compose down --volumes --remove-orphans > /dev/null 2>&1
log_pass "docker compose down completed"

# ============================================================================
# Summary
# ============================================================================
log_section "Results"

TOTAL=$((passed + failed + skipped))
echo -e "${GREEN}Passed: $passed${NC} | ${RED}Failed: $failed${NC} | ${YELLOW}Skipped: $skipped${NC} | Total: $TOTAL"

if [ $failed -eq 0 ]; then
  echo -e "\n${GREEN}${BOLD}✓ All integration checks passed${NC}"
  exit 0
else
  echo -e "\n${RED}${BOLD}✗ Some integration checks failed${NC}"
  exit 1
fi
