# Local Figma — AI 네이티브 UI 워크스페이스

> 자연어로 지시하면 AI가 웹 UI를 생성·수정하고, 실시간 미리보기에서 요소를 클릭해 정밀 편집할 수 있는 도구입니다.

---

## 목차

1. [프로젝트 개요](#프로젝트-개요)
2. [아키텍처 전체 구조](#아키텍처-전체-구조)
3. [디렉토리 구조](#디렉토리-구조)
4. [4개 서비스 상세](#4개-서비스-상세)
5. [핵심 처리 흐름](#핵심-처리-흐름)
6. [생성된 웹은 어디에 저장되는가?](#생성된-웹은-어디에-저장되는가)
7. [리전 마커 시스템](#리전-마커-시스템)
8. [셀렉션 오버레이 (요소 선택)](#셀렉션-오버레이-요소-선택)
9. [데이터베이스 스키마](#데이터베이스-스키마)
10. [빠른 시작](#빠른-시작)
11. [환경 변수](#환경-변수)
12. [개발 및 검증](#개발-및-검증)

---

## 프로젝트 개요

**Local Figma**는 4개의 Docker 서비스로 구성된 AI UI 프로토타이핑 도구입니다.

```
사용자가 채팅으로 "Gemini 스타일 챗봇 UI 만들어줘" 라고 입력하면
→ AI(GPT-4.1)가 완성된 HTML/CSS/JS 페이지를 생성하고
→ 실시간 미리보기에서 바로 확인할 수 있으며
→ 미리보기에서 요소를 클릭하고 "이 텍스트를 바꿔줘" 하면
→ 해당 부분만 정밀하게 수정합니다.
```

---

## 아키텍처 전체 구조

```
┌─────────────────────────────────────────────────────────┐
│                    사용자 브라우저                         │
│                                                         │
│  ┌──────────────────────┐  ┌──────────────────────────┐ │
│  │   채팅 패널 (Chat)    │  │  미리보기 패널 (Preview)  │ │
│  │                      │  │                          │ │
│  │  메시지 입력/표시     │  │  iframe (runtime:3001)   │ │
│  │  세션 관리           │  │  요소 클릭 → 선택         │ │
│  │  줌 컨트롤           │  │  오버레이 하이라이트       │ │
│  └──────────┬───────────┘  └──────────┬───────────────┘ │
│             │                         │ postMessage     │
│             │ HTTP POST               │ (selection.     │
│             │                         │  changed)       │
└─────────────┼─────────────────────────┼─────────────────┘
              │                         │
              ▼                         ▼
┌─────────────────────┐    ┌──────────────────────────┐
│   Web (Next.js)     │    │   Runtime (Node.js)      │
│   :3000             │    │   :3001                  │
│                     │    │                          │
│   operator-         │    │   workspace/preview/     │
│   workspace.tsx     │    │   index.html 서빙        │
│                     │    │   + selection-overlay.js  │
│   /api/orchestrate  │    │   주입                   │
│   (프록시)          │    │                          │
└────────┬────────────┘    └──────────────────────────┘
         │ HTTP POST                     ▲
         ▼                               │ 같은 volume
┌─────────────────────┐    ┌─────────────┴────────────┐
│   Agent (Python)    │    │   workspace/ (공유 볼륨)  │
│   :8123             │───▶│                          │
│                     │파일│   preview/index.html     │
│   LangGraph 파이프라인│쓰기│   .lfg-backups/          │
│   GPT-4.1 호출      │    │                          │
│   패치 실행          │    └──────────────────────────┘
└────────┬────────────┘
         │ SQL
         ▼
┌─────────────────────┐
│   PostgreSQL 16     │
│   :55432 (호스트)    │
│                     │
│   sessions          │
│   messages          │
│   patch_records     │
│   snapshots         │
└─────────────────────┘
```

---

## 디렉토리 구조

```
ui_agent/
├── apps/
│   ├── agent/                   # Python AI 에이전트 서비스
│   │   ├── local_figma_agent/   # 핵심 에이전트 패키지
│   │   │   ├── api.py           # FastAPI 엔드포인트 (/orchestrate, /health)
│   │   │   ├── orchestrator.py  # LangGraph 파이프라인 (5단계 노드 그래프)
│   │   │   ├── patch_executor.py# LLM 호출 → HTML 생성/수정 → 파일 저장
│   │   │   ├── file_service.py  # workspace/ 볼륨 읽기/쓰기/백업
│   │   │   ├── source_mapper.py # 선택된 요소 → 소스 코드 매핑 (4전략)
│   │   │   ├── providers.py     # OpenAI / Azure OpenAI 클라이언트
│   │   │   ├── repository.py    # PostgreSQL 세션/메시지 영속화
│   │   │   ├── models.py        # Pydantic 데이터 모델
│   │   │   ├── build_validator.py # 생성된 HTML 유효성 검증
│   │   │   └── config.py        # 환경 변수 로딩
│   │   ├── persistence/         # 범용 DB 저장소
│   │   ├── service/             # 비즈니스 서비스 레이어
│   │   ├── tests/               # pytest 테스트
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── runtime/                 # Node.js 정적 파일 서버
│   │   ├── server.mjs           # HTTP 서버 (workspace/ 내 HTML 서빙)
│   │   ├── selection-overlay.js # iframe에 주입되는 요소 선택 오버레이
│   │   └── Dockerfile
│   │
│   └── web/                     # Next.js 프론트엔드
│       ├── src/
│       │   ├── components/
│       │   │   └── operator-workspace.tsx  # 메인 워크스페이스 UI
│       │   └── lib/
│       │       ├── agent-api.ts            # Agent API 호출 래퍼
│       │       └── workspace-status.ts     # 서비스 상태 체크
│       ├── app/
│       │   ├── page.tsx                    # 메인 페이지
│       │   └── api/orchestrate/route.ts    # Agent 프록시 API
│       └── package.json
│
├── packages/                    # 공유 TypeScript 패키지 (모노레포)
│   ├── shared-types/            # 서비스 간 공유 타입 정의
│   ├── preview-bridge/          # iframe ↔ 호스트 postMessage 프로토콜
│   ├── design-schema/           # 디자인 인텐트 헬퍼
│   ├── memory/                  # 세션 메모리 헬퍼
│   ├── patch-engine/            # 패치 계획 타입
│   └── selection-adapter/       # 선택 오버레이 어댑터
│
├── infra/
│   └── migrations/              # PostgreSQL DDL 마이그레이션
│       ├── 0001_init.sql        # sessions, messages, patch_records, runtime_health
│       ├── 0002_persistence.sql # session_memory, selected_elements
│       ├── 0003_selection_payload_shape.sql
│       └── 0004_snapshots.sql   # 스냅샷 버전 관리
│
├── workspace/                   # ★ 생성된 웹 파일이 저장되는 공유 볼륨
│   ├── preview/
│   │   └── index.html           # AI가 생성/수정하는 HTML 파일
│   └── .lfg-backups/            # 패치 롤백용 백업 파일
│
├── docker-compose.yml           # 4개 서비스 오케스트레이션
└── .env                         # 환경 변수 (LLM 키 등)
```

---

## 4개 서비스 상세

### 1. PostgreSQL (postgres)
- **역할**: 세션, 대화 내역, 패치 기록, 스냅샷 영속화
- **포트**: 55432 (호스트) → 5432 (컨테이너)
- **데이터**: Docker 볼륨 `postgres-data`에 저장
- **초기화**: `infra/migrations/` 아래 SQL 파일이 컨테이너 시작 시 자동 실행

### 2. Agent (Python FastAPI + LangGraph)
- **역할**: 사용자 요청을 받아 LLM(GPT-4.1)으로 HTML을 생성·수정
- **포트**: 8123
- **핵심 엔드포인트**:
  - `GET /health` — 서비스 상태 확인
  - `POST /orchestrate` — 사용자 요청 → AI 처리 → HTML 생성/수정까지 원스톱 처리
  - `POST /provider/smoke` — LLM 연결 테스트
- **볼륨**: `./workspace` → `/app/workspace` (런타임과 공유)

### 3. Runtime (Node.js 22 정적 서버)
- **역할**: `workspace/preview/index.html`을 HTTP로 서빙하고, 셀렉션 오버레이 스크립트 주입
- **포트**: 3001
- **동작 모드**:
  - **편집 모드** (기본): HTML + `selection-overlay.js` 주입 → 요소 클릭 시 선택 이벤트 발생
  - **데모 모드** (`?demo=1`): HTML만 서빙 → 버튼/인풋 등 실제 인터랙션 가능
- **볼륨**: `./workspace` → `/app/workspace` (에이전트와 공유)

### 4. Web (Next.js 15 + React 19)
- **역할**: 사용자가 직접 사용하는 웹 UI — 채팅 패널 + 미리보기 패널
- **포트**: 3000
- **핵심 기능**:
  - 채팅 입력/표시 (세션 관리, 자동 세션 생성)
  - iframe으로 Runtime 서버의 미리보기 표시
  - 미리보기 확대/축소 (줌 컨트롤)
  - 요소 선택 상태 표시 및 수정 요청
  - 스냅샷 버전 관리
  - 데모 테스트 버튼 (새 창에서 인터랙션 가능한 버전 열기)

---

## 핵심 처리 흐름

### 흐름 1: 새 UI 생성 ("Gemini 스타일 챗봇 만들어줘")

```
사용자 입력
    │
    ▼
[Web] operator-workspace.tsx
    │ handleSendMessage()
    │ - 세션 없으면 자동 생성 (첫 30자로 세션 이름)
    │ - 스트리밍 상태 표시 (요청 해석 중 → 런타임 확인 중 → 패치 준비 중)
    │
    ▼
[Web] /api/orchestrate (Next.js API Route)
    │ Agent 서버로 프록시
    │
    ▼
[Agent] POST /orchestrate
    │
    ▼
[Agent] LangGraph 파이프라인 (5단계):
    │
    ├─ 1. classify_intent_node
    │     - 메시지 키워드 분석 → "create" | "modify" | "style-change" | "layout-restructure"
    │     - DesignIntent 추론 (화면 유형, 레이아웃, 밀도, 톤, 스타일 참조)
    │
    ├─ 2. project_state_load_node
    │     - PostgreSQL에서 세션 로드 (없으면 생성)
    │     - 메모리 스냅샷 로드
    │     - 프로젝트 매니페스트 구성 (workspace/ 파일 목록)
    │
    ├─ 3. planner_node
    │     - 패치 전략 결정: "create" | "update" | "targeted-update"
    │     - 선택된 요소가 있으면 source_mapper로 소스 매핑 보강
    │     - PatchPlan 생성 (대상 파일, 실행 단계, 검증 규칙)
    │
    ├─ 4. patch_execute_node
    │     - execute_create(): LLM에 프롬프트 전송 → HTML 코드 생성
    │     - workspace/preview/index.html에 파일 저장
    │     - 저장 전 기존 파일 백업 (.lfg-backups/)
    │     - 유효성 검증 실패 시 자동 롤백
    │
    └─ 5. response_formatting_node
          - 사용자/어시스턴트 메시지 PostgreSQL에 저장
          - 사용자 친화적 한국어 응답 생성
          - "✅ 워크스페이스를 생성했습니다. 변경 파일: index.html"
    │
    ▼
[Web] 응답 수신
    │ - 채팅에 에이전트 응답 표시
    │ - iframe 자동 새로고침 → Runtime이 새로 생성된 HTML 서빙
    │
    ▼
[Runtime] GET / → workspace/preview/index.html 서빙
    │ - selection-overlay.js 주입 (편집 모드)
    │
    ▼
사용자가 생성된 UI 확인 ✅
```

### 흐름 2: 요소 선택 후 수정 ("이 버튼의 텍스트를 바꿔줘")

```
사용자가 미리보기에서 요소 클릭
    │
    ▼
[Runtime iframe 내부] selection-overlay.js
    │ - click 이벤트 캡처 (capture: true, preventDefault + stopPropagation)
    │ - 클릭된 요소 분석:
    │   · CSS 선택자 생성 (id > data-lfg-component > nth-child)
    │   · DOM 경로 구축
    │   · 텍스트 스니펫 추출 (첫 120자)
    │   · 컴포넌트 힌트 (data-lfg-component 속성)
    │   · 소스 힌트 (data-lfg-source 속성 또는 리전 이름)
    │   · 요소 위치/크기 (bounds)
    │
    ▼
    postMessage("selection.changed", { id, selector, domPath, textSnippet, ... })
    │
    ▼
[Web] operator-workspace.tsx
    │ - message 이벤트 리스너가 수신
    │ - selectedElement 상태 업데이트
    │ - 선택 정보 패널에 표시 (선택자, 텍스트 스니펫, 바운드 등)
    │
    ▼
사용자가 "이 버튼 텍스트를 'Sign Up'으로 변경해줘" 입력
    │
    ▼
[Agent] orchestrate 호출 (selectedElement 포함)
    │
    ├─ classify_intent → "modify" (선택 요소 존재)
    ├─ planner → strategy: "targeted-update"
    │   └─ source_mapper: 선택 요소 → 리전 매핑 (4전략 신뢰도 기반)
    │      1순위: sourceHint.exportName
    │      2순위: componentHint
    │      3순위: DOM 경로의 컴포넌트 이름
    │      4순위: 선택자/텍스트 매칭
    │
    ├─ patch_execute → execute_targeted_update()
    │   - 대상 리전만 추출 (나머지 코드는 읽기 전용 참조)
    │   - LLM에 "이 리전만 수정하라" 프롬프트 전송
    │   - 규칙: 최소 변경 원칙 (텍스트만 바꾸라면 스타일은 유지)
    │   - replace_region()으로 해당 리전만 교체
    │   - 검증 실패 시 백업에서 자동 복원
    │
    └─ response_formatting → "✅ 요청하신 수정을 적용했습니다."
    │
    ▼
[Web] iframe 새로고침 → 수정된 UI 표시 ✅
```

### 흐름 3: 데모 테스트 ("만들어진 웹 사용해보기")

```
웹 UI의 "데모 테스트" 버튼 클릭
    │
    ▼
새 브라우저 창 열림: http://localhost:3001?demo=1
    │
    ▼
[Runtime] server.mjs
    │ - ?demo=1 감지 → selection-overlay.js 주입 안 함
    │ - 순수 HTML만 서빙
    │
    ▼
사용자가 버튼/입력/탭 등 실제 인터랙션 가능 ✅
(편집 모드에서는 클릭이 선택으로 가로채져서 인터랙션 불가)
```

---

## 생성된 웹은 어디에 저장되는가?

### 파일 시스템 (주요 저장소)

```
workspace/                          ← Docker 공유 볼륨 (agent + runtime)
├── preview/
│   └── index.html                  ← ★ AI가 생성/수정하는 메인 HTML 파일
└── .lfg-backups/
    └── plan-{hash}/
        └── preview/
            └── index.html          ← 패치 전 백업 (롤백용)
```

- **경로**: 호스트의 `ui_agent/workspace/preview/index.html`
- **Docker 볼륨 마운트**: `./workspace` → `/app/workspace` (agent + runtime 컨테이너 공유)
- Agent가 `file_service.py`의 `write_file("preview/index.html", generated_html)`로 저장
- Runtime이 같은 볼륨에서 `readFile(entryPath)`로 읽어서 서빙
- 환경 변수 `WORKSPACE_ROOT` (기본값: `/app/workspace`)로 경로 설정

### 데이터베이스 (메타데이터)

| 테이블 | 저장 내용 |
|--------|-----------|
| `sessions` | 세션 정보, 디자인 인텐트, 프로젝트 매니페스트 |
| `messages` | 사용자/어시스턴트 대화 내역 |
| `patch_records` | 패치 실행 기록 (변경 파일, 상태, 요약) |
| `snapshots` | 워크스페이스 스냅샷 (파일 아카이브 bytea) |

HTML 파일 자체는 파일 시스템에, 대화 기록과 패치 이력은 PostgreSQL에 저장됩니다.

---

## 리전 마커 시스템

AI가 생성하는 HTML에는 **리전 마커**가 포함됩니다. 이를 통해 전체 파일을 재생성하지 않고 특정 영역만 정밀하게 수정할 수 있습니다.

```html
<!-- @lfg-region:Header -->
<header data-lfg-component="Header">
  <h1>사이트 제목</h1>
  <nav>...</nav>
</header>
<!-- @lfg-region-end:Header -->

<!-- @lfg-region:Content -->
<main data-lfg-component="Content">
  <p>본문 내용</p>
</main>
<!-- @lfg-region-end:Content -->
```

- `<!-- @lfg-region:이름 -->` / `<!-- @lfg-region-end:이름 -->`: 리전 경계 주석
- `data-lfg-component="이름"`: 컴포넌트 식별 속성
- `data-lfg-source="파일:export:라인"`: 소스 매핑 속성 (선택 사항)

**targeted-update** 전략에서는:
1. 선택된 요소가 어떤 리전에 속하는지 감지 (`_detect_region_for_selection`)
2. 해당 리전의 내용만 추출 (`extract_region`)
3. LLM이 해당 리전만 수정한 결과를 반환
4. 기존 파일에서 해당 리전만 교체 (`replace_region`)

---

## 셀렉션 오버레이 (요소 선택)

Runtime이 제공하는 HTML에 자동 주입되는 `selection-overlay.js`는 미리보기에서 요소를 선택하는 기능을 제공합니다.

### 동작 방식
1. **마우스 이동**: 호버된 요소 위에 보라색 오버레이 표시
2. **가장 가까운 컴포넌트 조상** (`data-lfg-component`)으로 자동 확대
3. **클릭**: 요소 정보를 수집하여 `postMessage`로 호스트(Web)에 전달
4. **수집 정보**: CSS 선택자, DOM 경로, 텍스트 스니펫, 바운드(위치/크기), 컴포넌트 힌트, 소스 힌트

### 편집 모드 vs 데모 모드
| | 편집 모드 (기본) | 데모 모드 (`?demo=1`) |
|---|---|---|
| 오버레이 | ✅ 주입됨 | ❌ 주입 안 됨 |
| 클릭 동작 | 요소 선택 이벤트 발생 | 실제 버튼/링크 동작 |
| 용도 | 요소 선택 후 수정 요청 | 생성된 UI 인터랙션 테스트 |

---

## 데이터베이스 스키마

```sql
-- 세션 (대화 단위)
sessions (id, provider, design_intent, project_manifest, summary, created_at, updated_at)

-- 대화 메시지
messages (id, session_id, role, body, selected_element, selected_element_id, created_at)

-- 패치 실행 기록
patch_records (id, session_id, plan_id, patch_plan, status, files, files_changed, summary, created_at)

-- 런타임 상태
runtime_health (project_id, status, recorded_at)

-- 세션 메모리 (대화 맥락 유지)
session_memory (session_id, summary, structured_memory, created_at, updated_at)

-- 선택된 요소 기록
selected_elements (id, session_id, selector, dom_path, text_snippet, bounds, source_hint, captured_at)

-- 스냅샷 (버전 관리)
snapshots (id, session_id, label, workspace_archive, file_list, patch_record_id, created_at)
```

---

## 빠른 시작

### 사전 요구 사항
- Docker & Docker Compose
- OpenAI API 키 또는 Azure OpenAI 설정

### 1단계: 환경 변수 설정

```bash
cd ui_agent

# .env 파일 생성 (필수)
cat > .env << 'EOF'
# OpenAI 직접 사용 시
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1
OPENAI_API_KEY=sk-your-api-key

# Azure OpenAI 사용 시
# LLM_PROVIDER=azure-openai
# AZURE_OPENAI_API_KEY=your-key
# AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
# AZURE_OPENAI_DEPLOYMENT=your-deployment-name
# AZURE_OPENAI_API_VERSION=2024-10-21
EOF
```

### 2단계: 빌드 및 실행

```bash
docker compose up --build
```

4개 서비스가 의존성 순서대로 기동됩니다:
1. **postgres** (헬스체크 통과 후)
2. **agent** (postgres 준비 후 기동, 헬스체크 통과 후)
3. **runtime** (헬스체크 통과 후)
4. **web** (agent + runtime 준비 후 기동)

### 3단계: 사용

| URL | 설명 |
|-----|------|
| http://localhost:3000 | 웹 UI (채팅 + 미리보기) |
| http://localhost:3001 | 런타임 미리보기 (직접 접근) |
| http://localhost:3001?demo=1 | 데모 모드 (인터랙션 가능) |
| http://localhost:8123/health | 에이전트 상태 확인 |

### 포트 충돌 시

```bash
POSTGRES_HOST_PORT=55433 AGENT_HOST_PORT=8124 RUNTIME_HOST_PORT=3002 WEB_HOST_PORT=3003 docker compose up --build
```

---

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LLM_PROVIDER` | `openai` | LLM 제공자 (`openai` 또는 `azure-openai`) |
| `LLM_MODEL` | `gpt-4.1` | 사용할 모델 |
| `OPENAI_API_KEY` | — | OpenAI API 키 |
| `OPENAI_BASE_URL` | — | 커스텀 OpenAI 엔드포인트 |
| `AZURE_OPENAI_API_KEY` | — | Azure OpenAI 키 |
| `AZURE_OPENAI_ENDPOINT` | — | Azure OpenAI 엔드포인트 URL |
| `AZURE_OPENAI_DEPLOYMENT` | — | Azure 배포 이름 |
| `AZURE_OPENAI_API_VERSION` | `2024-10-21` | Azure API 버전 |
| `POSTGRES_DB` | `local_figma` | DB 이름 |
| `POSTGRES_USER` | `postgres` | DB 사용자 |
| `POSTGRES_PASSWORD` | `postgres` | DB 비밀번호 |
| `WORKSPACE_ROOT` | `/app/workspace` | 워크스페이스 루트 경로 (컨테이너 내부) |

---

## 개발 및 검증

### Docker 설정 확인
```bash
docker compose config
```

### 타입 체크 (TypeScript)
```bash
corepack pnpm install
corepack pnpm --filter @local-figma/web typecheck
```

### 에이전트 테스트 (Python)
```bash
cd apps/agent
pip install -e ".[dev]"
pytest tests/
```

### 개별 서비스 재빌드
```bash
docker compose build agent    # 에이전트만
docker compose build web      # 웹만
docker compose build runtime  # 런타임만
docker compose up -d           # 재시작
```

### 로그 확인
```bash
docker compose logs -f agent   # 에이전트 로그
docker compose logs -f web     # 웹 로그
docker compose logs -f runtime # 런타임 로그
```
