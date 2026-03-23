# Patch Engine Strategy

LFG-6에서 정의한 컴포넌트 단위 constrained editing과 파일 생성 전략을 문서화한다.

## 핵심 원칙

1. **생성은 open-ended, 수정은 constrained**
   - 새 화면 생성 → LLM이 전체 HTML 파일을 자유롭게 생성
   - 기존 화면 수정 → 선택된 컴포넌트/리전만 패치 (whole-file regeneration 회피)

2. **Region marker 기반 patch boundary 안정화**
   - 생성된 코드에 `<!-- @lfg-region:Name -->` / `<!-- @lfg-region-end:Name -->` 마커 삽입
   - 수정 시 마커로 대상 영역을 식별하여 해당 영역만 교체
   - 마커가 없는 레거시 파일은 full-file update로 fallback

3. **Selection context가 patch scope를 결정**
   - `SelectedElement.componentHint` → 우선 매칭 대상
   - `SelectedElement.selector` → 리전 내 콘텐츠 검색
   - 매칭 실패 시 → 안전하게 full-file update로 전환

## 전략 분류

| Strategy | 언제 | 동작 |
|----------|------|------|
| `create` | 사용자가 새 화면 요청 | LLM이 새 HTML 전체 생성 |
| `update` | selection 없이 기존 화면 변경 | 파일 전체를 LLM에 넘기고 수정본 수신 |
| `targeted-update` | selection 기반 변경 | 대상 region만 추출 → LLM에 전달 → region 교체 |
| `rollback` | 이전 상태 복구 | backup에서 복원 |

## Marker 체계

### Region markers

```html
<!-- @lfg-region:HeroSection -->
<section data-lfg-component="HeroSection">
  <h1>Welcome</h1>
  <p>Description here</p>
</section>
<!-- @lfg-region-end:HeroSection -->
```

- 모든 최상위 UI 섹션을 region marker로 감싼다
- `data-lfg-component` attribute를 root 요소에 부여
- Selection overlay에서 `componentHint`로 이 이름을 전달
- 마커 이름은 `[A-Za-z0-9_-]+` 패턴

### Source mapping

`SelectedElement.sourceHint`를 통해 파일 경로와 줄 번호 힌트를 전달:

```json
{
  "filePath": "preview/index.html",
  "exportName": "HeroSection",
  "line": 42
}
```

## 실행 흐름

```
User request
  → classify_intent (create | modify | style-change | layout-restructure)
  → project_state_load
  → planner (PatchPlan 생성)
  → patch_execute
      ├─ strategy=create    → _system_prompt_create → LLM → write_file
      ├─ strategy=update    → _system_prompt_update → LLM → write_file
      ├─ strategy=targeted  → detect_region → _system_prompt_targeted → LLM → replace_region
      └─ strategy=rollback  → restore_from_backup
  → validate_files (HTML parse + entry point check)
      ├─ pass → cleanup_backup, record status="applied"
      └─ fail → restore_from_backup, record status="failed"
  → response_formatting
  → persist patch_record
```

## Build validation

정적 HTML/CSS/JS 앱이므로 bundler 기반 빌드가 아닌 경량 검증:

1. **HTML 구조 검증**: HTMLParser로 파싱 가능 여부
2. **로컬 asset 참조 확인**: `src`/`href`가 가리키는 파일 존재 여부
3. **JS 균형 검사**: 중괄호/괄호/대괄호 균형
4. **Entry point 확인**: `preview/index.html` 존재 + 유효

## 실패 복구 경로

1. LLM 호출 실패 → 즉시 backup에서 원본 복원
2. Validation 실패 → backup에서 원본 복원 + 오류 메시지 surface
3. Rollback → 지정된 plan ID의 backup에서 복원
4. 모든 실패는 `PatchRecord.status="failed"`로 기록

## 파일 구조

```
apps/agent/local_figma_agent/
  ├── file_service.py       # 파일 read/write/backup/restore
  ├── patch_executor.py     # PatchPlan → 파일 조작 실행
  ├── build_validator.py    # HTML/JS/CSS 검증
  └── orchestrator.py       # LangGraph 노드에 patch_execute 통합

packages/patch-engine/src/
  └── index.ts              # TypeScript 타입 + region marker 유틸리티
```

## Component placement 규칙

- 생성된 파일은 `workspace/preview/` 디렉터리에 배치
- Entry point는 `preview/index.html`
- 추가 페이지 생성 시 `preview/{page-name}.html` 패턴
- CSS/JS 분리 시 `preview/styles/`, `preview/scripts/` 하위에 배치
- 이미지 등 asset은 `preview/assets/`에 배치
