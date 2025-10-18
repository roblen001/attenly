import React, { useEffect, useRef, useState } from "react";
import type { Quote } from "../../types";
import { api } from "../../libs/https";
import "./DocumentViewer.css";

// PDF.js v4
import * as pdfjsLib from "pdfjs-dist";
import "pdfjs-dist/web/pdf_viewer.css";
import {
  EventBus,
  PDFLinkService,
  PDFFindController,
  PDFViewer,
  PDFHistory,
} from "pdfjs-dist/web/pdf_viewer.mjs";
import pdfjsWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorkerUrl;

interface Props {
  quote: Quote;
  onClose: () => void;
  reportType?: "current" | "saved";
  reportId?: string;
  agentId?: string;
}

export default function PdfViewerWithHighlights({
  quote,
  onClose,
  reportType = "current",
  reportId,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const [loading, setLoading] = useState(true); // stays true until highlight centered OR error set
  const [err, setErr] = useState<string | null>(null);

  // Per-run objects
  const runIdRef = useRef(0);
  const loadingTaskRef = useRef<ReturnType<typeof pdfjsLib.getDocument> | null>(null);
  const eventBusRef = useRef<EventBus | null>(null);
  const viewerRef = useRef<PDFViewer | null>(null);
  const findControllerRef = useRef<PDFFindController | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Progress / watchdog to avoid false init errors when tab is backgrounded
  const progressRef = useRef({
    pagesInit: false,
    firstPageRendered: false,
    pagesLoaded: false,
  });
  const safetyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function clearSafetyTimer() {
    if (safetyTimerRef.current) {
      clearTimeout(safetyTimerRef.current);
      safetyTimerRef.current = null;
    }
  }

  function armSafetyWatchdog(ms = 45000) {
    clearSafetyTimer();

    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      const onVisible = () => {
        document.removeEventListener("visibilitychange", onVisible);
        armSafetyWatchdog(ms);
      };
      document.addEventListener("visibilitychange", onVisible);
      return;
    }

    safetyTimerRef.current = setTimeout(() => {
      const p = progressRef.current;
      if (!p.pagesInit && !p.firstPageRendered && !p.pagesLoaded) {
        setErr(
          "The PDF viewer didn't finish initializing. Check worker configuration and CORS."
        );
        setLoading(false);
      } else {
        // progress occurred; skip scary error
      }
    }, ms);
  }

  // 🔴 DO NOT TRIM the quotable text
  const quoteTextRaw = (quote as any)?.exact_text ?? quote.text ?? "";
  const precisePage = (quote as any)?.precise_page as number | undefined;

  const makePdfUrl = () => {
    if (reportType === "saved" && reportId) {
      return `/agents/reports/saved/${reportId}/documents/${quote.document_id}/file`;
    }
    return `/agents/documents/${quote.document_id}/file`;
  };

  // ---------- Utilities ----------
  const removeSoftHyphens = (s: string) => s.replace(/\u00ad/g, "");

  function collapseWithMap(original: string) {
    let collapsed = "";
    const mapOrigToCollapsed: number[] = new Array(original.length);
    const mapCollapsedToOrig: number[] = [];
    let lastWasSpace = false;

    for (let i = 0; i < original.length; i++) {
      const ch = original[i];
      const isSpace = /\s/.test(ch);

      if (isSpace) {
        if (!lastWasSpace) {
          collapsed += " ";
          mapCollapsedToOrig.push(i);
          lastWasSpace = true;
        }
        mapOrigToCollapsed[i] = collapsed.length - 1;
      } else {
        collapsed += ch;
        mapCollapsedToOrig.push(i);
        mapOrigToCollapsed[i] = collapsed.length - 1;
        lastWasSpace = false;
      }
    }

    if (collapsed.length > 0 && collapsed[0] === " ") {
      collapsed = collapsed.slice(1);
      mapCollapsedToOrig.shift();
      for (let i = 0; i < mapOrigToCollapsed.length; i++) {
        if (typeof mapOrigToCollapsed[i] === "number") {
          mapOrigToCollapsed[i] = Math.max(0, mapOrigToCollapsed[i] - 1);
        }
      }
    }
    if (collapsed.length > 0 && collapsed[collapsed.length - 1] === " ") {
      collapsed = collapsed.slice(0, -1);
      mapCollapsedToOrig.pop();
    }

    return { collapsed, mapOrigToCollapsed, mapCollapsedToOrig };
  }

  const waitForFirstHighlightAndCenter = async (
    viewerContainer: HTMLElement,
    timeoutMs = 3000
  ) => {
    const q = () =>
      viewerContainer.querySelector<HTMLElement>(".highlight.selected") ||
      viewerContainer.querySelector<HTMLElement>(".highlight");

    const already = q();
    if (already) {
      already.scrollIntoView({ block: "center", inline: "nearest" });
      return true;
    }

    return new Promise<boolean>((resolve) => {
      const obs = new MutationObserver(() => {
        const found = q();
        if (found) {
          found.scrollIntoView({ block: "center", inline: "nearest" });
          obs.disconnect();
          resolve(true);
        }
      });
      obs.observe(viewerContainer, { subtree: true, childList: true });
      setTimeout(() => {
        obs.disconnect();
        resolve(false);
      }, timeoutMs);
    });
  };

  const waitForFindStateReady = (eventBus: EventBus, timeoutMs = 1500) =>
    new Promise<void>((resolve) => {
      let settled = false;
      const onState = () => {
        if (settled) return;
        settled = true;
        eventBus.off("updatefindcontrolstate", onState);
        resolve();
      };
      eventBus.on("updatefindcontrolstate", onState);
      setTimeout(() => {
        if (settled) return;
        settled = true;
        eventBus.off("updatefindcontrolstate", onState);
        resolve();
      }, timeoutMs);
    });

  const levenshtein = (a: string, b: string) => {
    const m = a.length, n = b.length;
    if (m === 0) return n;
    if (n === 0) return m;
    const dp = new Uint16Array(n + 1);
    for (let j = 0; j <= n; j++) dp[j] = j;
    for (let i = 1; i <= m; i++) {
      let prev = dp[0];
      dp[0] = i;
      for (let j = 1; j <= n; j++) {
        const temp = dp[j];
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        dp[j] = Math.min(dp[j] + 1, dp[j - 1] + 1, prev + cost);
        prev = temp;
      }
    }
    return dp[n];
  };
  const simRatio = (a: string, b: string) => {
    const dist = levenshtein(a, b);
    const denom = Math.max(a.length, b.length) || 1;
    return 1 - dist / denom;
  };

  const getPageText = async (pdfDoc: any, pageNum: number) => {
    const page = await pdfDoc.getPage(pageNum);
    const tc = await page.getTextContent();
    return removeSoftHyphens(tc.items.map((i: any) => i.str).join(" "));
  };

  const fuzzyScanPage = async (pdfDoc: any, pageNum: number, needle: string) => {
    const original = await getPageText(pdfDoc, pageNum);
    if (!original) return null;

    const { collapsed: hay, mapCollapsedToOrig } = collapseWithMap(original);
    if (!hay) return null;

    const needleCollapsed = collapseWithMap(needle).collapsed;
    if (!needleCollapsed) return null;

    const hayL = hay.toLowerCase();
    const needleL = needleCollapsed.toLowerCase();

    const windowLen = Math.max(needleL.length, 12);
    if (windowLen > hayL.length) return null;

    const step = Math.max(5, Math.floor(windowLen / 6));
    let bestScore = 0;
    let bestStart = 0;

    for (let i = 0; i <= hayL.length - windowLen; i += step) {
      const window = hayL.slice(i, i + windowLen);
      const score = simRatio(window, needleL);
      if (score > bestScore) {
        bestScore = score;
        bestStart = i;
        if (bestScore >= 0.97) break;
      }
    }

    const refineRadius = 2 * step;
    const startRefine = Math.max(0, bestStart - refineRadius);
    const endRefine = Math.min(hayL.length - 1, bestStart + refineRadius);
    for (let i = startRefine; i <= endRefine; i++) {
      const window = hayL.slice(i, i + windowLen);
      const score = simRatio(window, needleL);
      if (score > bestScore) {
        bestScore = score;
        bestStart = i;
      }
    }

    const origStart = mapCollapsedToOrig[Math.max(0, bestStart)] ?? 0;
    const origEnd =
      mapCollapsedToOrig[Math.min(hayL.length - 1, bestStart + windowLen - 1)] ??
      original.length - 1;
    const snippet = original.slice(origStart, origEnd + 1);

    return { pageNum, score: bestScore, snippet };
  };

  const fuzzySearchDocument = async (pdfDoc: any, needle: string) => {
    const np = pdfDoc.numPages;
    const order: number[] = [];

    if (precisePage && precisePage >= 1 && precisePage <= np) {
      order.push(precisePage);
      for (let d = 1; d < np; d++) {
        if (precisePage - d >= 1) order.push(precisePage - d);
        if (precisePage + d <= np) order.push(precisePage + d);
      }
    } else {
      for (let p = 1; p <= np; p++) order.push(p);
    }

    let best: { pageNum: number; score: number; snippet: string } | null = null;

    for (const p of order) {
      const res = await fuzzyScanPage(pdfDoc, p, needle);
      if (!res) continue;
      if (!best || res.score > best.score) {
        best = res;
        if (best.score >= 0.92) break;
      }
    }
    return best;
  };

  const teardown = async () => {
    try { abortRef.current?.abort(); } catch {}
    try {
      const lt = loadingTaskRef.current;
      loadingTaskRef.current = null;
      await lt?.destroy();
    } catch {}
    try { eventBusRef.current = null; } catch {}
    viewerRef.current?.cleanup?.();
    viewerRef.current = null;
    findControllerRef.current = null;
    if (containerRef.current) containerRef.current.innerHTML = "";
  };

  useEffect(() => {
    const myRunId = ++runIdRef.current;

    (async () => {
      await teardown();

      // reset progress flags
      progressRef.current = { pagesInit: false, firstPageRendered: false, pagesLoaded: false };

      if (!quote?.document_id) {
        setErr("No document ID available for this quote.");
        setLoading(false);
        return;
      }
      if (!containerRef.current) {
        await new Promise((r) => requestAnimationFrame(() => r(null)));
        if (!containerRef.current) {
          setErr("Internal error: viewer container not mounted.");
          setLoading(false);
          return;
        }
      }

      try {
        setLoading(true);
        setErr(null);

        const pdfUrl = makePdfUrl();
        const ac = new AbortController();
        abortRef.current = ac;

        // Start watchdog AFTER we kick off network + worker
        armSafetyWatchdog(45000);

        let pdfRes: any;
        try {
          pdfRes = await api(pdfUrl, {
            headers: { Accept: "application/pdf" },
            responseType: "arraybuffer",
            withCredentials: true,
            signal: (ac as any).signal,
          } as any);
        } catch (e: any) {
          if ((ac as any).signal?.aborted) return;
          throw e;
        }

        let pdfBuf: ArrayBuffer;
        if (pdfRes && typeof pdfRes.arrayBuffer === "function") {
          if (!pdfRes.ok) throw new Error(`Failed to fetch PDF file: ${pdfRes.status}`);
          pdfBuf = await pdfRes.arrayBuffer();
        } else {
          const status = pdfRes?.status ?? 200;
          if (status < 200 || status >= 300) throw new Error(`Failed to fetch PDF file: ${status}`);
          pdfBuf = pdfRes.data as ArrayBuffer;
        }

        if (myRunId !== runIdRef.current) return;

        // Build DOM structure
        const container = containerRef.current!;
        container.innerHTML = "";
        const viewerElement = document.createElement("div");
        viewerElement.className = "pdfViewer";
        container.appendChild(viewerElement);

        // PDF.js wiring
        const eventBus = new EventBus();
        const linkService = new PDFLinkService({ eventBus });
        const findController = new PDFFindController({ eventBus, linkService });
        const history = new PDFHistory({ eventBus, linkService });

        eventBusRef.current = eventBus;
        findControllerRef.current = findController;

        linkService.setHistory(history);

        const viewer = new PDFViewer({
          container,
          viewer: viewerElement,
          eventBus,
          linkService,
          findController,
          textLayerMode: 1,
          annotationMode: 1,
        });
        viewerRef.current = viewer;
        linkService.setViewer(viewer);

        // Load doc
        const loadingTask = pdfjsLib.getDocument({ data: pdfBuf });
        loadingTaskRef.current = loadingTask;

        let pdfDoc: any;
        try {
          pdfDoc = await loadingTask.promise;
        } catch (e) {
          if (myRunId !== runIdRef.current) return;
          throw e;
        }

        if (myRunId !== runIdRef.current) return;

        viewer.setDocument(pdfDoc);
        linkService.setDocument(pdfDoc);
        findController.setDocument?.(pdfDoc);

        const fingerprint: string =
          (pdfDoc as any).fingerprint ||
          (pdfDoc as any).fingerprints?.[0] ||
          "fallback";
        history.initialize({ fingerprint });

        // events
        const onPagesInit = () => {
          if (myRunId !== runIdRef.current) return;
          progressRef.current.pagesInit = true; // progress
          const initialPage =
            precisePage && precisePage >= 1 && precisePage <= pdfDoc.numPages
              ? precisePage
              : 1;
          viewer.currentPageNumber = initialPage;
          viewer.currentScaleValue = "page-width";
        };

        const onPageRendered = () => {
          progressRef.current.firstPageRendered = true; // progress
          // once rendering is happening, watchdog can be cleared
          clearSafetyTimer();
        };

        const onPagesLoaded = async () => {
          if (myRunId !== runIdRef.current) return;

          progressRef.current.pagesLoaded = true; // progress

          // Let layout/text layers settle
          await new Promise((r) => requestAnimationFrame(() => r(null)));
          await new Promise((r) => setTimeout(r, 0));

          const qExact = quoteTextRaw;
          let centered = false;

          // (1) exact find with RAW quote
          if (qExact && qExact.length) {
            eventBus.dispatch("find", {
              type: "find",
              query: qExact,
              caseSensitive: false,
              entireWord: false,
              highlightAll: true,
              phraseSearch: true,
            } as any);

            await waitForFindStateReady(eventBus);

            eventBus.dispatch("findagain", {
              type: "findagain",
              findPrevious: false,
              highlightAll: true,
              phraseSearch: true,
            } as any);

            centered = await waitForFirstHighlightAndCenter(container, 2500);
          }

          // (2) fuzzy fallback
          if (!centered && qExact && qExact.length) {
            const fuzzy = await fuzzySearchDocument(pdfDoc, qExact);

            if (fuzzy) {
              const { pageNum, snippet } = fuzzy;
              viewer.currentPageNumber = pageNum;

              const normalizedSnippet = collapseWithMap(snippet).collapsed;

              eventBus.dispatch("find", {
                type: "find",
                query: normalizedSnippet,
                caseSensitive: false,
                entireWord: false,
                highlightAll: true,
                phraseSearch: true,
              } as any);

              await waitForFindStateReady(eventBus);

              eventBus.dispatch("findagain", {
                type: "findagain",
                findPrevious: false,
                highlightAll: true,
                phraseSearch: true,
              } as any);

              centered = await waitForFirstHighlightAndCenter(container, 2500);
            }
          }

          // Reveal or error:
          if (centered) {
            setLoading(false); // highlight centered -> show viewer
          } else {
            setErr("Couldn't locate the quote in this PDF.");
            setLoading(false); // show error overlay
          }
        };

        eventBus.on("pagesinit", onPagesInit as any);
        eventBus.on("pagesloaded", onPagesLoaded as any);
        eventBus.on("pagerendered", onPageRendered as any);

      } catch (e: any) {
        if (myRunId !== runIdRef.current) return;
        console.error("[PDF] fatal error:", e);
        setErr(e?.message ?? "Failed to load PDF.");
        setLoading(false);
      }
    })();

    return () => {
      clearSafetyTimer();
      try {
        const bus = eventBusRef.current;
        if (bus) {
          // We don't have direct refs to the bound callbacks in this scope; PDF.js tolerates off with undefined.
          bus.off("pagesinit", undefined as any);
          bus.off("pagesloaded", undefined as any);
          bus.off("pagerendered", undefined as any);
        }
      } catch {}
      teardown();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quote.document_id, reportId, reportType]);

  const jumpToQuote = () => {
    const bus = eventBusRef.current;
    const container = containerRef.current!;
    if (bus && quoteTextRaw) {
      bus.dispatch("findagain", {
        type: "findagain",
        findPrevious: false,
        highlightAll: true,
        phraseSearch: true,
      } as any);
      setTimeout(() => {
        const sel =
          container.querySelector<HTMLElement>(".highlight.selected") ||
          container.querySelector<HTMLElement>(".highlight");
        if (!sel) {
          console.warn("[PDF] Jump requested but no highlight present.");
        }
        sel?.scrollIntoView({ block: "center", inline: "nearest" });
      }, 120);
    }
  };

  // keyboard shortcuts: J = jump, Esc = close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key.toLowerCase() === "j") jumpToQuote();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, quoteTextRaw]);

  return (
    <div className="document-viewer-overlay">
      {/* Compact corner controls */}
      <div className="floating-controls">
        {quoteTextRaw && (
          <button className="btn-primary" onClick={jumpToQuote} title="Jump to Quote (J)">
            <span>🎯</span>
            Jump to Quote
          </button>
        )}
        <button className="btn-primary" onClick={onClose} title="Close (Esc)">
          <span>✕</span>
          Close
        </button>
      </div>

      {/* Viewer region – larger height for readability */}
      <div className="document-content">
        <div className="content-container" style={{ position: "relative", height: "100%" }}>
          <div
            ref={containerRef}
            className="viewerContainer"
            // Hide viewer completely until loading finishes
            style={{
              position: "absolute",
              inset: 0,
              overflow: "auto",
              background: "#2b2b2b",
              opacity: loading ? 0 : 1,
              pointerEvents: loading ? "none" : "auto",
              transition: "opacity 160ms ease",
            }}
          />
          {loading && !err && (
            <div
              className="loading-overlay"
              style={{
                position: "absolute",
                inset: 0,
                display: "grid",
                placeItems: "center",
                background: "var(--background-overlay)",
                zIndex: 100, // ensure above PDF layers
              }}
            >
              <div style={{ textAlign: "center", color: "var(--text-primary)" }}>
                <div className="pdf-loading-icon">📄</div>
                <p style={{ margin: 0, fontSize: "var(--font-size-base)", fontWeight: 600 }}>
                  Loading PDF…
                </p>
                {quoteTextRaw ? (
                  <p style={{ 
                    opacity: 0.85, 
                    marginTop: "var(--spacing-sm)", 
                    fontSize: "var(--font-size-sm)" 
                  }}>
                    Finding quote in document…
                  </p>
                ) : null}
                <div className="pdf-progress-bar">
                  <div className="pdf-progress-fill"></div>
                </div>
              </div>
            </div>
          )}
          {err && (
            <div
              className="error-overlay"
              style={{
                position: "absolute",
                inset: 0,
                display: "grid",
                placeItems: "center",
                background: "rgba(0,0,0,0.55)",
                zIndex: 100,
              }}
            >
              <div className="error-state" style={{ textAlign: "center", color: "#eee" }}>
                <p style={{ marginBottom: 8 }}>Error: {err}</p>
                <p style={{ opacity: 0.85 }}>
                  Ensure the endpoint returns <code>application/pdf</code> and CORS/Range headers
                  are allowed if you send credentials.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
