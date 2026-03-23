# Local Figma – Operator Runbook

운영자가 Local Figma 시스템을 시작하고 사용하기 위한 가이드.

## 사전 요구사항

- Docker Desktop (Docker Compose v2 포함)
- LLM 자격 증명 (OpenAI 또는 Azure OpenAI)

## 1. 환경 설정

```bash
cd ui_agent/
cp .env.example .env
```

`.env` 파일에서 LLM provider 설정:

**OpenAI 사용 시:**
```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1
OPENAI_API_KEY=sk-...
```

**Azure OpenAI 사용 시:**
```env
LLM_PROVIDER=azure
LLM_MODEL=gpt-4.1
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

## 2. 서비스 시작

```bash
# 빌드 + 시작
docker compose up --build -d

# 로그 확인
docker compose logs -f
```

서비스 4개가 시작됩니다:

| 서비스 | URL | 역할 |
|--------|-----|------|
| **web** | http://localhost:3000 | 운영자 워크스페이스 (채팅 + 프리뷰) |
| **agent** | http://localhost:8123 | LangGraph 오케스트레이션 + 패치 엔진 |
| **runtime** | http://localhost:3001 | 생성된 앱 프리뷰 서버 |
| **postgres** | localhost:55432 | 세션/메시지/패치 이력 저장 |

## 3. 상태 확인

```bash
# 전체 상태
curl http://localhost:8123/health | python3 -m json.tool

# 확인 포인트:
# - provider.providerReady: true  → LLM 연결 됨
# - databaseReady: true           → DB 연결 됨
# - langgraph: "ready"            → 오케스트레이터 준비 됨
```

```bash
# 런타임 상태
curl http://localhost:3001/health | python3 -m json.tool

# status: "ready" → 프리뷰 파일 존재
```

## 4. 사용 흐름

### 시나리오 1: 새 화면 생성

1. http://localhost:3000 접속
2. 채팅 입력란에 요청 입력:
   > "Create a modern dashboard with a hero banner, key metrics grid, and a sidebar"
3. **Send request** 클릭
4. agent가 LLM을 호출하여 HTML 생성 → workspace에 파일 저장
5. 우측 iframe이 자동 새로고침되어 결과 표시
6. 하단 **Diff / patch status** 패널에서 상태 확인:
   - Patch status: **applied**
   - Files changed: preview/index.html

### 시나리오 2: 선택 기반 수정

1. 프리뷰 iframe에서 수정할 요소 클릭
2. 하단 **Selected element context** 패널에 선택 정보 표시
3. 채팅 입력란에 수정 요청:
   > "Change the header background to dark blue and make the title white"
4. **Send request** 클릭
5. agent가 선택된 영역만 targeted-update로 패치
6. iframe 자동 새로고침

### 시나리오 3: 세션 복원

```bash
# API로 세션 복원 확인
curl http://localhost:8123/sessions/{sessionId}/restore | python3 -m json.tool

# 반환 내용:
# - session: 세션 메타데이터
# - memory: 요약 + structured memory
# - messages: 전체 대화 이력
# - selectedElements: 선택 이력
# - patchRecords: 패치 적용 이력
```

## 5. 통합 테스트

```bash
# 자동화된 통합 테스트 실행
./scripts/integration-test.sh

# 빌드 건너뛰기 (이미 빌드된 경우)
./scripts/integration-test.sh --skip-build
```

테스트 항목:
- docker compose config 검증
- 4개 서비스 기동 확인
- DB + LLM provider 연결 확인
- 새 화면 생성 시나리오
- 선택 기반 수정 시나리오
- 세션 복원 시나리오
- workspace 파일 존재 확인
- compose down 정리

## 6. 트러블슈팅

### Agent가 degraded 상태

```bash
# provider 설정 확인
curl http://localhost:8123/health | python3 -m json.tool
```

→ `providerReady: false`이면 `.env`에서 LLM 자격 증명 확인

### Runtime이 error 상태

→ `workspace/preview/index.html`이 없는 경우. 채팅으로 화면 생성 요청 필요.

### DB 연결 실패

```bash
# postgres 로그 확인
docker compose logs postgres

# 마이그레이션 수동 실행
docker compose exec postgres psql -U postgres -d local_figma -f /docker-entrypoint-initdb.d/0001_init.sql
```

### Patch 실패 후 복구

패치 실패 시 원본 파일이 자동 복구됩니다. 수동 확인:

```bash
# workspace 파일 목록
curl http://localhost:8123/workspace/files | python3 -m json.tool

# 특정 파일 내용
curl "http://localhost:8123/workspace/file?path=preview/index.html"
```

## 7. 서비스 중지

```bash
# 중지 (데이터 보존)
docker compose down

# 중지 + 데이터 삭제
docker compose down --volumes --remove-orphans
```

## 8. 주요 API 엔드포인트

| Method | Path | 용도 |
|--------|------|------|
| GET | `/health` | agent 상태 |
| POST | `/orchestrate` | 채팅 요청 처리 (계획 + 패치 실행) |
| POST | `/execute-patch` | 단독 패치 실행 |
| GET | `/workspace/files` | workspace 파일 목록 |
| GET | `/workspace/file?path=...` | 파일 내용 조회 |
| POST | `/sessions` | 세션 생성 |
| GET | `/sessions/{id}/restore` | 세션 전체 복원 |
| POST | `/sessions/{id}/patch-records` | 패치 기록 저장 |
| GET | `/sessions/{id}/patch-records` | 패치 이력 조회 |
