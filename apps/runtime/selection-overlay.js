/**
 * Selection overlay script – injected by the runtime server into every preview HTML.
 *
 * Responsibilities:
 * 1. Highlight hovered elements that have `data-lfg-component` (or parent with it)
 * 2. On click, build a SelectedElement payload with accurate componentHint + sourceHint
 * 3. Send `selection.changed` event via postMessage to the host
 * 4. Handle `host.ready` / `runtime.ping` / `runtime.reload` from the host
 */
(function () {
  "use strict";

  var BRIDGE_VERSION = "2026-03-19";
  var SOURCE = "runtime";

  // ── Helpers ───────────────────────────────────────────────────────────

  function sendToHost(type, payload) {
    if (!window.parent || window.parent === window) return;
    window.parent.postMessage(
      { version: BRIDGE_VERSION, source: SOURCE, type: type, payload: payload },
      "*"
    );
  }

  function generateId() {
    return "sel-" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
  }

  // ── DOM introspection ────────────────────────────────────────────────

  /**
   * Build a CSS selector for an element.
   * Prefers id > data-lfg-component > nth-child path.
   */
  function buildSelector(el) {
    if (el.id) return "#" + CSS.escape(el.id);
    if (el.dataset && el.dataset.lfgComponent) {
      return "[data-lfg-component=\"" + el.dataset.lfgComponent + "\"]";
    }
    var parts = [];
    var current = el;
    while (current && current !== document.body && current !== document.documentElement) {
      var tag = current.tagName.toLowerCase();
      if (current.id) {
        parts.unshift("#" + CSS.escape(current.id) + " > " + parts.shift());
        break;
      }
      if (current.dataset && current.dataset.lfgComponent) {
        parts.unshift("[data-lfg-component=\"" + current.dataset.lfgComponent + "\"]");
        break;
      }
      var parent = current.parentElement;
      if (parent) {
        var siblings = Array.from(parent.children).filter(function (c) {
          return c.tagName === current.tagName;
        });
        if (siblings.length > 1) {
          var idx = siblings.indexOf(current) + 1;
          tag += ":nth-of-type(" + idx + ")";
        }
      }
      parts.unshift(tag);
      current = parent;
    }
    return parts.join(" > ");
  }

  /**
   * Build a DOM path array (tag names from root to element).
   */
  function buildDomPath(el) {
    var path = [];
    var current = el;
    while (current && current !== document) {
      var tag = current.tagName ? current.tagName.toLowerCase() : "";
      if (tag) {
        if (current.dataset && current.dataset.lfgComponent) {
          tag += "[" + current.dataset.lfgComponent + "]";
        } else if (current.id) {
          tag += "#" + current.id;
        }
        path.unshift(tag);
      }
      current = current.parentNode;
    }
    return path;
  }

  /**
   * Walk up the tree to find the nearest ancestor (or self) with data-lfg-component.
   */
  function findComponentAncestor(el) {
    var current = el;
    while (current && current !== document.body) {
      if (current.dataset && current.dataset.lfgComponent) {
        return current;
      }
      current = current.parentElement;
    }
    return null;
  }

  /**
   * Find the nearest region marker comment around an element.
   * Walks up the DOM and checks preceding siblings/comments for @lfg-region markers.
   */
  function findRegionFromComments(el) {
    var current = el;
    while (current && current !== document.body) {
      // Check preceding siblings for region start comment
      var sibling = current.previousSibling;
      while (sibling) {
        if (sibling.nodeType === Node.COMMENT_NODE) {
          var match = sibling.textContent.match(/@lfg-region:([A-Za-z0-9_-]+)/);
          if (match) return match[1];
        }
        sibling = sibling.previousSibling;
      }
      current = current.parentElement;
    }
    return null;
  }

  /**
   * Extract text snippet from element (first 120 chars of visible text).
   */
  function extractTextSnippet(el) {
    var text = (el.textContent || "").trim().replace(/\s+/g, " ");
    return text.length > 120 ? text.slice(0, 120) + "…" : text;
  }

  /**
   * Build sourceHint from data attributes and region context.
   */
  function buildSourceHint(el, componentAncestor, regionName) {
    var hint = { filePath: "preview/index.html" };

    // Check for explicit source annotation
    if (el.dataset && el.dataset.lfgSource) {
      var parts = el.dataset.lfgSource.split(":");
      hint.filePath = parts[0] || hint.filePath;
      if (parts[1]) hint.exportName = parts[1];
      if (parts[2]) hint.line = parseInt(parts[2], 10);
      return hint;
    }

    if (componentAncestor && componentAncestor.dataset.lfgSource) {
      var cparts = componentAncestor.dataset.lfgSource.split(":");
      hint.filePath = cparts[0] || hint.filePath;
      if (cparts[1]) hint.exportName = cparts[1];
      if (cparts[2]) hint.line = parseInt(cparts[2], 10);
      return hint;
    }

    // Use region/component name as exportName
    if (regionName) {
      hint.exportName = regionName;
    } else if (componentAncestor && componentAncestor.dataset.lfgComponent) {
      hint.exportName = componentAncestor.dataset.lfgComponent;
    }

    return hint;
  }

  // ── Overlay ──────────────────────────────────────────────────────────

  var overlay = document.createElement("div");
  overlay.id = "__lfg-selection-overlay";
  overlay.style.cssText =
    "position:fixed;pointer-events:none;z-index:2147483647;" +
    "border:2px solid #8b5cf6;background:rgba(139,92,246,0.08);" +
    "border-radius:4px;transition:all 0.15s ease;display:none;";

  var label = document.createElement("div");
  label.style.cssText =
    "position:absolute;top:-22px;left:-2px;background:#8b5cf6;color:#fff;" +
    "font:bold 11px/1 system-ui,sans-serif;padding:3px 6px;border-radius:3px 3px 0 0;" +
    "white-space:nowrap;max-width:250px;overflow:hidden;text-overflow:ellipsis;";
  overlay.appendChild(label);

  document.addEventListener("DOMContentLoaded", function () {
    document.body.appendChild(overlay);
  });

  var currentTarget = null;

  document.addEventListener("mousemove", function (e) {
    var el = document.elementFromPoint(e.clientX, e.clientY);
    if (!el || el === overlay || overlay.contains(el)) return;

    // Prefer component ancestor for highlight
    var comp = findComponentAncestor(el);
    var target = comp || el;

    if (target === currentTarget) return;
    currentTarget = target;

    var rect = target.getBoundingClientRect();
    overlay.style.display = "block";
    overlay.style.left = rect.left + "px";
    overlay.style.top = rect.top + "px";
    overlay.style.width = rect.width + "px";
    overlay.style.height = rect.height + "px";

    // Label shows component name or tag
    var name = (target.dataset && target.dataset.lfgComponent) || target.tagName.toLowerCase();
    if (target.id) name += "#" + target.id;
    label.textContent = name;
  }, { passive: true });

  document.addEventListener("mouseleave", function () {
    overlay.style.display = "none";
    currentTarget = null;
  });

  // ── Click capture ────────────────────────────────────────────────────

  document.addEventListener("click", function (e) {
    // Ignore if the target is a link or button that should navigate
    if (e.target.closest("a[href]") && !e.altKey) return;

    e.preventDefault();
    e.stopPropagation();

    var el = e.target;
    var componentAncestor = findComponentAncestor(el);
    var regionName = findRegionFromComments(componentAncestor || el);
    var targetEl = componentAncestor || el;
    var rect = targetEl.getBoundingClientRect();

    var payload = {
      id: generateId(),
      sessionId: "",  // filled by host
      kind: "element",
      selector: buildSelector(targetEl),
      domPath: buildDomPath(targetEl),
      textSnippet: extractTextSnippet(targetEl),
      bounds: {
        x: rect.left + window.scrollX,
        y: rect.top + window.scrollY,
        width: rect.width,
        height: rect.height,
      },
      componentHint: (componentAncestor && componentAncestor.dataset.lfgComponent) || regionName || null,
      sourceHint: buildSourceHint(el, componentAncestor, regionName),
      capturedAt: new Date().toISOString(),
    };

    sendToHost("selection.changed", payload);

    // Flash the overlay
    overlay.style.borderColor = "#22d3ee";
    overlay.style.background = "rgba(34,211,238,0.15)";
    setTimeout(function () {
      overlay.style.borderColor = "#8b5cf6";
      overlay.style.background = "rgba(139,92,246,0.08)";
    }, 300);
  }, true);

  // ── Bridge message handling ──────────────────────────────────────────

  function buildHealthPayload() {
    return {
      buildId: document.querySelector("meta[name=lfg-build-id]")
        ? document.querySelector("meta[name=lfg-build-id]").content
        : String(Date.now()),
      lastHeartbeatAt: new Date().toISOString(),
      projectId: "local-figma-preview",
      runtimeUrl: window.location.origin,
      status: "ready",
    };
  }

  window.addEventListener("message", function (event) {
    var data = event.data;
    if (!data || data.version !== BRIDGE_VERSION || data.source === SOURCE) return;

    if (data.type === "host.ready") {
      sendToHost("runtime.ready", {
        health: buildHealthPayload(),
        previewPath: "/preview",
      });
    }

    if (data.type === "runtime.ping") {
      sendToHost("runtime.health", buildHealthPayload());
    }

    if (data.type === "runtime.reload") {
      window.location.reload();
    }
  });

  // Auto-announce on load
  sendToHost("runtime.ready", {
    health: buildHealthPayload(),
    previewPath: "/preview",
  });
})();
