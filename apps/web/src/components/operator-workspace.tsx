"use client";

import { useEffect, useRef, useState } from "react";
import { PREVIEW_BRIDGE_VERSION, isPreviewBridgeEvent } from "@local-figma/preview-bridge";
import type { PreviewBridgeToHostEvent } from "@local-figma/preview-bridge";
import type { MessageRole, RuntimeHealth, SelectedElement } from "@local-figma/shared-types";
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

const seedSessions: SessionSummary[] = [
  { id: "session-041", label: "HOW-41 Workspace Shell", state: "live", lastAction: "Chat and preview scaffolding" },
  { id: "session-018", label: "Selection Overlay Spike", state: "review", lastAction: "Awaiting adapter contract" },
  { id: "session-006", label: "Runtime Bootstrap", state: "archived", lastAction: "Placeholder page mounted" },
];

const initialMessages: UiMessage[] = [
  {
    id: "assistant-welcome",
    role: "assistant",
    content:
      "Describe the workspace you want to shape. I will keep the request in-session, show runtime health, and prepare the preview surface for targeted edits.",
    timestamp: new Date().toISOString(),
    status: "done",
  },
];

const streamStages = ["Interpreting request", "Checking runtime health", "Preparing patch outline"];
const bridgeHint = "runtime.reload";

function formatTime(iso: string) {
  return new Intl.DateTimeFormat("en", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
}

function buildAssistantReply(prompt: string, status: WorkspaceStatusSnapshot) {
  const normalized = prompt.trim().replace(/\s+/g, " ");
  const runtimeLine =
    status.runtime.state === "ready"
      ? "The live runtime is reachable, so preview-side iteration can stay in the loop."
      : "The runtime still needs attention, so I would keep edits scoped until the preview stabilizes.";
  const agentLine =
    status.agent.state === "ready"
      ? "Agent connectivity looks healthy enough for a real orchestration handoff."
      : "Agent health is visible, but credentials are incomplete, so this response is staying in mock-stream mode.";

  return `I captured the request: "${normalized}". ${runtimeLine} ${agentLine} Next, I would break the change into chat-shell updates, preview adjustments, and a narrow patch plan tied to the selected region or active thread.`;
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
  const sourceHint = element.sourceHint?.filePath ? ` in ${element.sourceHint.filePath}` : "";
  return `${element.selector}${sourceHint}`;
}

export function OperatorWorkspace({
  initialStatus,
  runtimeUrl,
}: {
  initialStatus: WorkspaceStatusSnapshot;
  runtimeUrl: string;
}) {
  const [status, setStatus] = useState(initialStatus);
  const [messages, setMessages] = useState(initialMessages);
  const [composer, setComposer] = useState("");
  const [activeSessionId, setActiveSessionId] = useState(seedSessions[0]?.id ?? "");
  const [streamStage, setStreamStage] = useState<string | null>(null);
  const [iframeNonce, setIframeNonce] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [bridgeState, setBridgeState] = useState<BridgeState>({
    state: "connecting",
    buildId: "Unknown",
    lastEvent: "Waiting for runtime",
    runtimeStatus: initialStatus.runtime.summary,
  });
  const [selectedElement, setSelectedElement] = useState<string>("Selection details will appear here once the preview adapter emits a target.");
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const runtimeOrigin = new URL(runtimeUrl).origin;

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshStatus();
    }, 10000);

    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
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
        setSelectedElement(summarizeSelectedElement(message.payload));
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
      lastEvent: `${mode === "reconnecting" ? "Reconnecting" : "Connecting"} bridge`,
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
      lastEvent: "Hard refreshing iframe",
    }));
    setIframeNonce((current) => current + 1);
  }

  function requestRuntimeReload() {
    setBridgeState((current) => ({
      ...current,
      state: "reconnecting",
      lastEvent: "runtime.reload requested",
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

  async function handleSendMessage() {
    const prompt = composer.trim();
    if (!prompt) {
      return;
    }

    const timestamp = new Date().toISOString();
    const assistantId = `assistant-${crypto.randomUUID()}`;
    const reply = buildAssistantReply(prompt, status);
    const stageWindow = Math.max(1, Math.floor(reply.length / streamStages.length));

    setMessages((current) => [
      ...current,
      { id: `user-${crypto.randomUUID()}`, role: "user", content: prompt, timestamp, status: "done" },
      { id: assistantId, role: "assistant", content: "", timestamp: new Date().toISOString(), status: "streaming" },
    ]);
    setComposer("");
    setStreamStage(streamStages[0] ?? null);

    for (let index = 1; index <= reply.length; index += 1) {
      if (index % stageWindow === 0) {
        const nextStage = streamStages[Math.min(streamStages.length - 1, Math.floor(index / stageWindow))];
        setStreamStage(nextStage ?? streamStages.at(-1) ?? null);
      }

      const partial = reply.slice(0, index);
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId ? { ...message, content: partial, status: index === reply.length ? "done" : "streaming" } : message,
        ),
      );
      await sleep(16);
    }

    setStreamStage(null);
  }

  return (
    <main className={styles.page}>
      <section className={styles.shell}>
        <aside className={styles.sessions}>
          <div className={styles.brandBlock}>
            <p className={styles.eyebrow}>Operator Workspace</p>
            <h1>Local Figma</h1>
            <p className={styles.brandCopy}>
              Natural-language iteration, live runtime preview, and room for selection-based edits once the adapter lands.
            </p>
          </div>

          <div className={styles.sessionList}>
            <div className={styles.sectionHeader}>
              <h2>Sessions</h2>
              <span>3 tracked</span>
            </div>
            {seedSessions.map((session) => (
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
            ))}
          </div>

          <div className={styles.sidePanel}>
            <div className={styles.sectionHeader}>
              <h2>Status</h2>
              <button className={styles.ghostButton} onClick={() => void refreshStatus()} type="button">
                {isRefreshing ? "Refreshing..." : "Refresh"}
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
        </aside>

        <section className={styles.chatColumn}>
          <div className={styles.topBar}>
            <div>
              <p className={styles.eyebrow}>Thread</p>
              <h2>Main workspace conversation</h2>
            </div>
            <div className={styles.topBarMeta}>
              <span>Active session: {activeSessionId}</span>
              <span>Checked {formatTime(status.checkedAt)}</span>
            </div>
          </div>

          <div className={styles.chatFeed}>
            {messages.map((message) => (
              <article key={message.id} className={message.role === "assistant" ? styles.assistantBubble : styles.userBubble}>
                <div className={styles.messageMeta}>
                  <strong>{message.role === "assistant" ? "Operator Agent" : "You"}</strong>
                  <span>{formatTime(message.timestamp)}</span>
                </div>
                <p>{message.content || "..."}</p>
                {message.status === "streaming" ? <small className={styles.streamingTag}>Streaming reply</small> : null}
              </article>
            ))}
          </div>

          <div className={styles.composerCard}>
            <label className={styles.composerLabel} htmlFor="workspace-prompt">
              Describe the UI change
            </label>
            <textarea
              id="workspace-prompt"
              className={styles.composer}
              onChange={(event) => setComposer(event.target.value)}
              placeholder="Example: tighten the layout, keep Slack-like density, and leave room for a selected-card edit flow."
              rows={5}
              value={composer}
            />
            <div className={styles.composerFooter}>
              <div className={styles.stageBlock}>
                <span className={styles.eyebrow}>Streaming stage</span>
                <strong>{streamStage ?? "Idle"}</strong>
              </div>
              <button className={styles.primaryButton} onClick={() => void handleSendMessage()} type="button">
                Send request
              </button>
            </div>
          </div>

          <div className={styles.bottomPanels}>
            <section className={styles.placeholderPanel}>
              <div className={styles.sectionHeader}>
                <h2>Diff / patch status</h2>
                <span>Placeholder</span>
              </div>
              <p>
                Reserve this surface for patch plans, file deltas, and rollback state once the patch engine and runtime edit loop are
                connected.
              </p>
            </section>
            <section className={styles.placeholderPanel}>
              <div className={styles.sectionHeader}>
                <h2>Selected element context</h2>
                <span>Adapter seam</span>
              </div>
              <p>{selectedElement}</p>
              <p>
                The preview bridge is ready for events like <code>{bridgeHint}</code>. Selection payloads land here once the runtime
                emits them.
              </p>
            </section>
          </div>
        </section>

        <section className={styles.previewColumn}>
          <div className={styles.previewHeader}>
            <div>
              <p className={styles.eyebrow}>Preview</p>
              <h2>Live runtime iframe</h2>
            </div>
            <div className={styles.previewActions}>
              <button className={styles.ghostButton} onClick={() => handshakeBridge("reconnecting")} type="button">
                Reconnect bridge
              </button>
              <button className={styles.ghostButton} onClick={() => requestRuntimeReload()} type="button">
                Runtime reload
              </button>
              <button className={styles.ghostButton} onClick={() => reloadPreview()} type="button">
                Reload iframe
              </button>
            </div>
          </div>

          <article className={styles.previewStatusCard}>
            <div className={styles.healthHeader}>
              <strong>Runtime connection</strong>
              <span className={`${styles.statePill} ${getStatusTone(status.runtime.state)}`}>{status.runtime.summary}</span>
            </div>
            <p>{status.runtime.detail}</p>
            <code>{runtimeUrl}</code>
          </article>

          <section className={styles.previewTelemetry}>
            <article className={styles.telemetryCard}>
              <span className={styles.telemetryLabel}>Bridge</span>
              <strong>{bridgeState.state}</strong>
            </article>
            <article className={styles.telemetryCard}>
              <span className={styles.telemetryLabel}>Runtime</span>
              <strong>{bridgeState.runtimeStatus}</strong>
            </article>
            <article className={styles.telemetryCard}>
              <span className={styles.telemetryLabel}>Build</span>
              <strong>{bridgeState.buildId}</strong>
            </article>
            <article className={styles.telemetryCard}>
              <span className={styles.telemetryLabel}>Last event</span>
              <strong>{bridgeState.lastEvent}</strong>
            </article>
          </section>

          <div className={styles.iframeFrame}>
            <iframe
              ref={iframeRef}
              key={iframeNonce}
              className={styles.previewIframe}
              onLoad={() => handshakeBridge("connecting")}
              src={runtimeUrl}
              title="Local Figma runtime preview"
            />
          </div>
        </section>
      </section>
    </main>
  );
}
