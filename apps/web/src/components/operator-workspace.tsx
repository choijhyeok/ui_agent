"use client";

import { useEffect, useRef, useState } from "react";
import { PREVIEW_BRIDGE_VERSION, isPreviewBridgeEvent } from "@local-figma/preview-bridge";
import type { PreviewBridgeToHostEvent } from "@local-figma/preview-bridge";
import type { MessageRole, PatchPlan, RuntimeHealth, SelectedElement } from "@local-figma/shared-types";
import type { OrchestrationResponse } from "@/src/lib/agent-api";
import type { WorkspaceStatusSnapshot } from "@/src/lib/workspace-status";
import styles from "./operator-workspace.module.css";

type UiMessage = {
  id: string;
  role: Exclude<MessageRole, "system" | "tool">;
  content: string;
  timestamp: string;
  status: "done" | "streaming";
};

type SessionSummary = {
  id: string;
  label: string;
  state: "live" | "review" | "archived";
  lastAction: string;
};

type BridgeState = {
  state: "connecting" | "connected" | "reconnecting" | "reloading";
  buildId: string;
  lastEvent: string;
  runtimeStatus: string;
};

type SnapshotSummary = {
  id: string;
  sessionId: string;
  label: string;
  fileCount: number;
  files: string[];
  patchRecordId: string | null;
  createdAt: string;
};

const streamStages = ["요청 해석 중", "런타임 상태 확인 중", "패치 계획 준비 중"];
const bridgeHint = "runtime.reload";

function formatTime(iso: string) {
  return new Intl.DateTimeFormat("ko", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
}

function buildAssistantReply(prompt: string, status: WorkspaceStatusSnapshot) {
  const normalized = prompt.trim().replace(/\s+/g, " ");
  const runtimeLine =
    status.runtime.state === "ready"
      ? "라이브 런타임에 연결 가능하여 프리뷰 반복 작업을 진행할 수 있습니다."
      : "런타임에 주의가 필요하여 프리뷰가 안정될 때까지 편집 범위를 제한합니다.";
  const agentLine =
    status.agent.state === "ready"
      ? "에이전트 연결이 정상이며 오케스트레이션 핸드오프가 가능합니다."
      : "에이전트 상태는 확인되지만 자격 증명이 불완전하여 모의 스트림 모드로 응답합니다.";

  return `요청을 캡처했습니다: "${normalized}". ${runtimeLine} ${agentLine} 다음으로 채팅 셸 업데이트, 프리뷰 조정, 선택 영역에 연결된 패치 계획으로 변경 사항을 분리합니다.`;
}

function getStatusTone(state: WorkspaceStatusSnapshot["agent"]["state"]) {
  if (state === "ready") {
    return styles.ready;
  }
  if (state === "degraded") {
    return styles.degraded;
  }
  return styles.error;
}

async function sleep(ms: number) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

function formatRuntimeHealth(health: RuntimeHealth) {
  return {
    buildId: health.buildId,
    lastEvent: `runtime.health @ ${new Date(health.lastHeartbeatAt).toLocaleTimeString()}`,
    runtimeStatus: health.status,
    state: "connected" as const,
  };
}

function summarizeSelectedElement(element: SelectedElement) {
  const componentHint = element.componentHint ? ` (${element.componentHint})` : "";
  return `${element.kind}: ${element.selector}${componentHint}`;
}

function formatBounds(bounds: SelectedElement["bounds"]) {
  return `${Math.round(bounds.x)}, ${Math.round(bounds.y)} ${Math.round(bounds.width)}x${Math.round(bounds.height)}`;
}

function isRuntimeHealth(value: unknown): value is RuntimeHealth {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<RuntimeHealth>;
  return (
    typeof candidate.projectId === "string" &&
    typeof candidate.status === "string" &&
    typeof candidate.runtimeUrl === "string" &&
    typeof candidate.buildId === "string" &&
    typeof candidate.lastHeartbeatAt === "string"
  );
}

export function OperatorWorkspace({
  initialStatus,
  runtimeUrl,
}: {
  initialStatus: WorkspaceStatusSnapshot;
  runtimeUrl: string;
}) {
  const [status, setStatus] = useState(initialStatus);
  const [messages, setMessages] = useState<UiMessage[]>(() => [
    {
      id: "assistant-welcome",
      role: "assistant",
      content:
        "원하는 워크스페이스를 설명해 주세요. 요청을 세션에 유지하고, 런타임 상태를 표시하며, 선택 기반 편집을 위한 프리뷰 영역을 준비합니다.",
      timestamp: initialStatus.checkedAt,
      status: "done",
    },
  ]);
  const [composer, setComposer] = useState("");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState("");
  const [streamStage, setStreamStage] = useState<string | null>(null);
  const [previewZoom, setPreviewZoom] = useState(100);
  const [iframeNonce, setIframeNonce] = useState(0);
  const [iframeLoaded, setIframeLoaded] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);
  const [bridgeState, setBridgeState] = useState<BridgeState>({
    state: "connecting",
    buildId: "알 수 없음",
    lastEvent: "런타임 대기 중",
      runtimeStatus: initialStatus.runtime.summary,
  });
  const [selectedElement, setSelectedElement] = useState<SelectedElement | null>(null);
  const [selectionStatus, setSelectionStatus] = useState("프리뷰에서 요소를 클릭하거나 영역을 드래그하여 선택 컨텍스트를 캡처하세요.");
  const [latestPatchPlan, setLatestPatchPlan] = useState<PatchPlan | null>(null);
  const [latestPatchRecord, setLatestPatchRecord] = useState<OrchestrationResponse["patchRecord"]>(null);
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [snapshotBusy, setSnapshotBusy] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const runtimeOrigin = new URL(runtimeUrl).origin;

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshStatus();
    }, 10000);

    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!activeSessionId) return;
    setSelectedElement(null);
    setLatestPatchPlan(null);
    setSelectionStatus("프리뷰에서 요소를 클릭하거나 영역을 드래그하면 선택 컨텍스트가 캡처됩니다.");
    void loadSnapshots();
    if (iframeLoaded) {
      handshakeBridge("reconnecting");
    }
  }, [activeSessionId, iframeLoaded]);

  useEffect(() => {
    setIsHydrated(true);
  }, []);

  useEffect(() => {
    async function persistSelection(nextSelection: SelectedElement) {
      setSelectedElement(nextSelection);
      setSelectionStatus("선택 페이로드 저장 중...");

      try {
        const response = await fetch(`/api/sessions/${activeSessionId}/selected-elements`, {
          method: "POST",
          headers: {
            "content-type": "application/json",
          },
          body: JSON.stringify({
            ...nextSelection,
            sessionId: activeSessionId,
          }),
        });
        const payload = (await response.json()) as
          | { persisted: boolean; selectedElement: SelectedElement }
          | { error: string };

        if (!response.ok || "error" in payload) {
          throw new Error("error" in payload ? payload.error : `HTTP ${response.status}`);
        }

        setSelectedElement(payload.selectedElement);
        setSelectionStatus(payload.persisted ? "활성 세션에 선택 페이로드가 저장되었습니다." : "선택이 로컬에 캡처되었으나 영속성 저장소를 사용할 수 없습니다.");
      } catch (error) {
        setSelectionStatus(error instanceof Error ? error.message : "선택 영속성 저장에 실패했습니다.");
      }
    }

    function handleBridgeMessage(event: MessageEvent) {
      if (event.origin !== runtimeOrigin || !isPreviewBridgeEvent(event.data) || event.data.source !== "runtime") {
        return;
      }

      const message = event.data as PreviewBridgeToHostEvent;
      if (message.type === "runtime.ready") {
        setBridgeState(formatRuntimeHealth(message.payload.health));
        return;
      }

      if (message.type === "runtime.health") {
        setBridgeState(formatRuntimeHealth(message.payload));
        return;
      }

      if (message.type === "runtime.reloaded") {
        setBridgeState((current) => ({
          ...current,
          state: "connected",
          lastEvent: `runtime.reloaded (${message.payload.reason})`,
        }));
        return;
      }

      if (message.type === "selection.changed") {
        void persistSelection(message.payload);
      }
    }

    window.addEventListener("message", handleBridgeMessage);
    return () => window.removeEventListener("message", handleBridgeMessage);
  }, [runtimeOrigin]);

  function sendBridgeMessage(type: "host.ready" | "runtime.ping" | "runtime.reload", payload: Record<string, string>) {
    if (!iframeRef.current?.contentWindow) {
      return;
    }

    iframeRef.current.contentWindow.postMessage(
      {
        version: PREVIEW_BRIDGE_VERSION,
        source: "web",
        type,
        payload,
      },
      runtimeOrigin,
    );
  }

  function handshakeBridge(mode: "connecting" | "reconnecting") {
    setBridgeState((current) => ({
      ...current,
      state: mode,
      lastEvent: `${mode === "reconnecting" ? "브릿지 재연결" : "브릿지 연결"} 중`,
    }));

    sendBridgeMessage("host.ready", {
      sentAt: new Date().toISOString(),
      sessionId: activeSessionId,
    });
    sendBridgeMessage("runtime.ping", {
      requestedAt: new Date().toISOString(),
    });
  }

  function reloadPreview() {
    setBridgeState((current) => ({
      ...current,
      state: "reloading",
      lastEvent: "iframe 새로고침 중",
    }));
    setIframeNonce((current) => current + 1);
  }

  function requestRuntimeReload() {
    setBridgeState((current) => ({
      ...current,
      state: "reconnecting",
      lastEvent: "runtime.reload 요청됨",
    }));
    sendBridgeMessage("runtime.reload", {
      requestedAt: new Date().toISOString(),
      reason: "operator-refresh",
    });
  }

  async function refreshStatus() {
    try {
      setIsRefreshing(true);
      const response = await fetch("/api/workspace-status", { cache: "no-store" });
      if (!response.ok) {
        return;
      }

      const nextStatus = (await response.json()) as WorkspaceStatusSnapshot;
      setStatus(nextStatus);
    } finally {
      setIsRefreshing(false);
    }
  }

  async function loadSnapshots() {
    try {
      const response = await fetch(`/api/sessions/${activeSessionId}/snapshots`, { cache: "no-store" });
      if (response.ok) {
        const data = (await response.json()) as SnapshotSummary[];
        setSnapshots(data);
      }
    } catch {
      // 스냅샷 로드 실패는 무시
    }
  }

  async function handleCreateSnapshot() {
    setSnapshotBusy(true);
    try {
      const label = `v${snapshots.length + 1}`;
      const response = await fetch(`/api/sessions/${activeSessionId}/snapshots`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          label,
          patchRecordId: latestPatchRecord?.id ?? null,
        }),
      });
      if (response.ok) {
        await loadSnapshots();
      }
    } finally {
      setSnapshotBusy(false);
    }
  }

  async function handleRestoreSnapshot(snapshotId: string) {
    setSnapshotBusy(true);
    try {
      const response = await fetch(`/api/snapshots/${snapshotId}/restore`, {
        method: "POST",
      });
      if (response.ok) {
        reloadPreview();
      }
    } finally {
      setSnapshotBusy(false);
    }
  }

  async function handleNewSession() {
    const newId = `session-${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
    const newSession: SessionSummary = {
      id: newId,
      label: `새 세션`,
      state: "live",
      lastAction: "생성됨",
    };
    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newId);
    setMessages([{
      id: "assistant-welcome",
      role: "assistant",
      content: "원하는 워크스페이스를 설명해 주세요. 요청을 세션에 유지하고, 런타임 상태를 표시하며, 선택 기반 편집을 위한 프리뷰 영역을 준비합니다.",
      timestamp: new Date().toISOString(),
      status: "done",
    }]);
    setSelectedElement(null);
    setLatestPatchPlan(null);
    setLatestPatchRecord(null);
    setSnapshots([]);
  }

  async function handleSendMessage() {
    const prompt = composer.trim();
    if (!prompt) {
      return;
    }

    // 세션이 없으면 자동 생성
    let currentSessionId = activeSessionId;
    if (!currentSessionId) {
      const newId = `session-${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
      const newSession: SessionSummary = {
        id: newId,
        label: prompt.slice(0, 30) + (prompt.length > 30 ? "..." : ""),
        state: "live",
        lastAction: "생성됨",
      };
      setSessions((prev) => [newSession, ...prev]);
      setActiveSessionId(newId);
      currentSessionId = newId;
    } else {
      // 첫 메시지면 세션 라벨 업데이트
      setSessions((prev) =>
        prev.map((s) =>
          s.id === currentSessionId && s.label === "새 세션"
            ? { ...s, label: prompt.slice(0, 30) + (prompt.length > 30 ? "..." : "") }
            : s
        )
      );
    }

    const timestamp = new Date().toISOString();
    const assistantId = `assistant-${crypto.randomUUID()}`;

    setMessages((current) => [
      ...current,
      { id: `user-${crypto.randomUUID()}`, role: "user", content: prompt, timestamp, status: "done" },
      { id: assistantId, role: "assistant", content: "", timestamp: new Date().toISOString(), status: "streaming" },
    ]);
    setComposer("");
    setStreamStage(streamStages[0] ?? null);

    try {
      await sleep(80);
      setStreamStage(streamStages[1] ?? null);

      const response = await fetch("/api/orchestrate", {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify({
          sessionId: currentSessionId,
          message: prompt,
          selectedElement,
          runtimeStatus: isRuntimeHealth(status.runtime.raw) ? status.runtime.raw : undefined,
        }),
      });
      const payload = (await response.json()) as OrchestrationResponse | { error: string };

      if (!response.ok || "error" in payload) {
        throw new Error("error" in payload ? payload.error : `HTTP ${response.status}`);
      }

      setStreamStage(streamStages[2] ?? null);
      setLatestPatchPlan(payload.patchPlan);
      setLatestPatchRecord(payload.patchRecord ?? null);
      setBridgeState(formatRuntimeHealth(payload.runtimeStatus));

      // Auto-reload preview when patch was applied successfully
      if (payload.patchRecord && payload.patchRecord.status === "applied") {
        reloadPreview();
        // 세션 상태 업데이트
        setSessions((prev) =>
          prev.map((s) =>
            s.id === currentSessionId
              ? { ...s, lastAction: payload.patchRecord?.summary?.slice(0, 40) ?? "패치 적용됨", state: "live" }
              : s
          )
        );
      }

      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId ? { ...message, content: payload.response, status: "done" } : message,
        ),
      );
    } catch (error) {
      const fallback = buildAssistantReply(prompt, status);
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content: `${fallback} 오케스트레이션 실패: ${error instanceof Error ? error.message : "알 수 없는 오류"}.`,
                status: "done",
              }
            : message,
        ),
      );
    } finally {
      setStreamStage(null);
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.shell}>
        <aside className={styles.sessions}>
          <div className={styles.brandBlock}>
            <p className={styles.eyebrow}>오퍼레이터 워크스페이스</p>
            <h1>Local Figma</h1>
            <p className={styles.brandCopy}>
              자연어 반복, 라이브 런타임 프리뷰, 선택 기반 편집을 지원하는 AI UI 워크스페이스.
            </p>
          </div>

          <div className={styles.sessionList}>
            <div className={styles.sectionHeader}>
              <h2>세션</h2>
              <button className={styles.ghostButton} onClick={() => void handleNewSession()} type="button">+ 새 세션</button>
            </div>
            {sessions.length === 0 ? (
              <p style={{ fontSize: "0.85rem", opacity: 0.7, padding: "8px 0" }}>세션이 없습니다. 새 세션을 만들거나 채팅을 시작하세요.</p>
            ) : (
              sessions.map((session) => (
                <button
                  key={session.id}
                  className={session.id === activeSessionId ? styles.sessionItemActive : styles.sessionItem}
                  onClick={() => setActiveSessionId(session.id)}
                  type="button"
                >
                  <strong>{session.label}</strong>
                  <span>{session.lastAction}</span>
                  <small>{session.state}</small>
                </button>
              ))
            )}
          </div>

          <div className={styles.sidePanel}>
            <div className={styles.sectionHeader}>
              <h2>상태</h2>
              <button className={styles.ghostButton} onClick={() => void refreshStatus()} type="button">
                {isRefreshing ? "새로고침 중..." : "새로고침"}
              </button>
            </div>
            <div className={styles.healthStack}>
              {[status.agent, status.runtime].map((service) => (
                <article key={service.label} className={styles.healthCard}>
                  <div className={styles.healthHeader}>
                    <strong>{service.label}</strong>
                    <span className={`${styles.statePill} ${getStatusTone(service.state)}`}>{service.summary}</span>
                  </div>
                  <p>{service.detail}</p>
                  <code>{service.url}</code>
                </article>
              ))}
            </div>
          </div>

          <div className={styles.sidePanel}>
            <div className={styles.sectionHeader}>
              <h2>스냅샷</h2>
              <button
                className={styles.ghostButton}
                onClick={() => void handleCreateSnapshot()}
                disabled={snapshotBusy}
                type="button"
              >
                {snapshotBusy ? "처리 중..." : "현재 버전 저장"}
              </button>
            </div>
            {snapshots.length === 0 ? (
              <p style={{ fontSize: "0.85rem", opacity: 0.7 }}>저장된 스냅샷이 없습니다. 현재 상태를 저장해두면 언제든 복구할 수 있습니다.</p>
            ) : (
              <div className={styles.healthStack}>
                {snapshots.map((snap) => (
                  <article key={snap.id} className={styles.healthCard}>
                    <div className={styles.healthHeader}>
                      <strong>{snap.label || snap.id}</strong>
                      <span style={{ fontSize: "0.75rem", opacity: 0.7 }}>
                        {snap.fileCount}개 파일
                      </span>
                    </div>
                    <p style={{ fontSize: "0.8rem" }}>
                      {new Date(snap.createdAt).toLocaleString("ko")}
                    </p>
                    <button
                      className={styles.ghostButton}
                      onClick={() => void handleRestoreSnapshot(snap.id)}
                      disabled={snapshotBusy}
                      type="button"
                    >
                      이 버전으로 복구
                    </button>
                  </article>
                ))}
              </div>
            )}
          </div>
        </aside>

        <section className={styles.chatColumn}>
          <div className={styles.topBar}>
            <div>
              <p className={styles.eyebrow}>스레드</p>
              <h2>대화 창</h2>
            </div>
            <div className={styles.topBarMeta}>
              <span>활성 세션: {activeSessionId}</span>
              <span>확인 {isHydrated ? formatTime(status.checkedAt) : "--:--"}</span>
            </div>
          </div>

          <div className={styles.chatFeed}>
            {messages.map((message) => (
              <article key={message.id} className={message.role === "assistant" ? styles.assistantBubble : styles.userBubble}>
                <div className={styles.messageMeta}>
                  <strong>{message.role === "assistant" ? "오퍼레이터 에이전트" : "나"}</strong>
                  <span>{isHydrated ? formatTime(message.timestamp) : "--:--"}</span>
                </div>
                <p>{message.content || "..."}</p>
                {message.status === "streaming" ? <small className={styles.streamingTag}>응답 스트리밍 중</small> : null}
              </article>
            ))}
          </div>

          <div className={styles.composerCard}>
            <label className={styles.composerLabel} htmlFor="workspace-prompt">
              UI 변경 사항을 설명하세요
            </label>
            <textarea
              id="workspace-prompt"
              className={styles.composer}
              onChange={(event) => setComposer(event.target.value)}
              placeholder="예시: 레이아웃을 조밀하게 하고, Slack 스타일의 밀도를 유지하며, 선택된 카드 편집 플로우를 위한 공간을 남겨주세요."
              rows={5}
              value={composer}
            />
            <div className={styles.composerFooter}>
              <div className={styles.stageBlock}>
                <span className={styles.eyebrow}>스트리밍 단계</span>
                <strong>{streamStage ?? "대기 중"}</strong>
              </div>
              <button className={styles.primaryButton} onClick={() => void handleSendMessage()} type="button">
                요청 보내기
              </button>
            </div>
          </div>

          <div className={styles.bottomPanels}>
            <section className={styles.placeholderPanel}>
              <div className={styles.sectionHeader}>
                <h2>분비 / 패치 상태</h2>
                <span>{latestPatchPlan ? latestPatchPlan.strategy : "대기 중"}</span>
              </div>
              {latestPatchPlan ? (
                <>
                  <p>플래너 대상: {latestPatchPlan.target.intentSummary}</p>
                  <p>파일: {latestPatchPlan.target.files.join(", ") || "아직 파일이 확정되지 않았습니다"}</p>
                  <p>단계: {latestPatchPlan.steps.join(" ")}</p>
                  {latestPatchRecord ? (
                    <>
                      <p>패치 상태: <strong>{latestPatchRecord.status}</strong></p>
                      <p>변경된 파일: {latestPatchRecord.filesChanged.join(", ") || "없음"}</p>
                      <p>요약: {latestPatchRecord.summary}</p>
                    </>
                  ) : null}
                </>
              ) : (
                <p>요청을 보내면 플래너 응답이 여기에 표시됩니다.</p>
              )}
            </section>
            <section className={styles.placeholderPanel}>
              <div className={styles.sectionHeader}>
                <h2>선택된 요소 컨텍스트</h2>
                <span>{selectedElement ? selectedElement.kind : "대기 중"}</span>
              </div>
              {selectedElement ? (
                <>
                  <p>{summarizeSelectedElement(selectedElement)}</p>
                  <p>영역: {formatBounds(selectedElement.bounds)}</p>
                  <p>메모: {selectedElement.note || "캡처된 메모 없음"}</p>
                  <p>컴포넌트 힌트: {selectedElement.componentHint || "추론되지 않음"}</p>
                  <p>저장 상태: {selectionStatus}</p>
                </>
              ) : (
                <>
                  <p>{selectionStatus}</p>
                  <p>
                    프리뷰 브릿지가 <code>{bridgeHint}</code> 같은 이벤트를 수신할 준비가 되었습니다. 런타임이 선택 이벤트를 발생시키면 여기에 표시됩니다.
                  </p>
                </>
              )}
            </section>
          </div>
        </section>

        <section className={styles.previewColumn}>
          <div className={styles.previewHeader}>
            <div>
              <p className={styles.eyebrow}>프리뷰</p>
              <h2>라이브 런타임</h2>
            </div>
            <div className={styles.previewActions}>
              <button
                className={styles.primaryButton}
                onClick={() => window.open(`${runtimeUrl}?demo=1`, "_blank", "noopener")}
                type="button"
                style={{ fontSize: "0.8rem", padding: "4px 12px" }}
              >
                데모 테스트
              </button>
              <button className={styles.ghostButton} onClick={() => setPreviewZoom((z) => Math.min(z + 25, 200))} type="button">+</button>
              <span style={{ fontSize: "0.8rem", minWidth: "3em", textAlign: "center" }}>{previewZoom}%</span>
              <button className={styles.ghostButton} onClick={() => setPreviewZoom((z) => Math.max(z - 25, 25))} type="button">−</button>
              <button className={styles.ghostButton} onClick={() => setPreviewZoom(100)} type="button">초기화</button>
              <button className={styles.ghostButton} onClick={() => reloadPreview()} type="button">
                새로고침
              </button>
            </div>
          </div>

          <article className={styles.previewStatusCard}>
            <div className={styles.healthHeader}>
              <strong>런타임 연결</strong>
              <span className={`${styles.statePill} ${getStatusTone(status.runtime.state)}`}>{status.runtime.summary}</span>
            </div>
            <p>{status.runtime.detail}</p>
            <code>{runtimeUrl}</code>
          </article>

          <section className={styles.previewTelemetry}>
            <article className={styles.telemetryCard}>
              <span className={styles.telemetryLabel}>브릿지</span>
              <strong>{bridgeState.state}</strong>
            </article>
            <article className={styles.telemetryCard}>
              <span className={styles.telemetryLabel}>런타임</span>
              <strong>{bridgeState.runtimeStatus}</strong>
            </article>
            <article className={styles.telemetryCard}>
              <span className={styles.telemetryLabel}>빌드</span>
              <strong>{bridgeState.buildId}</strong>
            </article>
            <article className={styles.telemetryCard}>
              <span className={styles.telemetryLabel}>마지막 이벤트</span>
              <strong>{bridgeState.lastEvent}</strong>
            </article>
          </section>

          <div className={styles.iframeFrame}>
            <div style={{ width: "100%", height: "100%", overflow: "auto" }}>
              <iframe
                ref={iframeRef}
                key={iframeNonce}
                className={styles.previewIframe}
                style={{
                  transform: `scale(${previewZoom / 100})`,
                  transformOrigin: "top left",
                  width: `${10000 / previewZoom}%`,
                  height: `${10000 / previewZoom}%`,
                }}
                onLoad={() => {
                  setIframeLoaded(true);
                  handshakeBridge("connecting");
                }}
                src={runtimeUrl}
                title="Local Figma 런타임 프리뷰"
              />
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}
