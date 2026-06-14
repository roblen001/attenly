import { useEffect, useRef, useState } from "react";
import type { Quote, DocumentBoundingBoxes, WordSpan } from "../../types";
import { api } from "../../libs/https";
import {
  createOverlayCanvas,
  drawBoundingBoxes,
  getPageViewport,
  removeAllOverlayCanvases,
} from "../../utils/bboxRenderer";
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

  // BBox support state
  const [, setBboxData] = useState<DocumentBoundingBoxes | null>(null);
  const [, setHasBboxSupport] = useState(false);

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

  const scrollContainerToBBox = (
    container: HTMLElement,
    pageEl: HTMLElement,
    canvas: HTMLCanvasElement,
    bbox: number[] // [x0, y0, x1, y1] normalized
  ) => {
    if (!container || !pageEl || !canvas || !bbox || bbox.length !== 4) {
      return;
    }

    const containerRect = container.getBoundingClientRect();
    const pageRect = pageEl.getBoundingClientRect();

    // Bbox center in normalized coordinates [0, 1]
    const bboxCenterXNorm = (bbox[0] + bbox[2]) / 2;
    const bboxCenterYNorm = (bbox[1] + bbox[3]) / 2;

    // Convert to pixels using CSS size (not internal canvas resolution)
    const bboxCenterXInPage = bboxCenterXNorm * canvas.clientWidth;
    const bboxCenterYInPage = bboxCenterYNorm * canvas.clientHeight;

    // Compute bbox center in viewport coordinates
    const bboxCenterXInViewport = pageRect.left + bboxCenterXInPage;
    const bboxCenterYInViewport = pageRect.top + bboxCenterYInPage;

    // We want the bbox center at the container's center
    const targetCenterX = containerRect.left + container.clientWidth / 2;
    const targetCenterY = containerRect.top + container.clientHeight / 2;

    // Calculate scroll deltas
    const deltaX = bboxCenterXInViewport - targetCenterX;
    const deltaY = bboxCenterYInViewport - targetCenterY;

    // Apply smooth scroll
    container.scrollTo({
      left: container.scrollLeft + deltaX,
      top: container.scrollTop + deltaY,
      behavior: 'smooth',
    });
  };

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

  const convertHighlightToNormalizedBBox = (
    highlightEl: HTMLElement,
    pageEl: HTMLElement
  ): number[] | null => {
    try {
      const pageRect = pageEl.getBoundingClientRect();
      const highlightRect = highlightEl.getBoundingClientRect();
      
      // Calculate position relative to page element
      const relativeX = highlightRect.left - pageRect.left;
      const relativeY = highlightRect.top - pageRect.top;
      
      // Normalize to [0, 1] using page element dimensions (not canvas)
      // This ensures we're working in the same coordinate space as the page layout
      const x0Norm = relativeX / pageRect.width;
      const y0Norm = relativeY / pageRect.height;
      const x1Norm = (relativeX + highlightRect.width) / pageRect.width;
      const y1Norm = (relativeY + highlightRect.height) / pageRect.height;
      
      // Log for debugging - verify normalized coordinates look reasonable
      console.log('[PDF Highlight] Normalized bbox:', {
        normalized: [x0Norm, y0Norm, x1Norm, y1Norm],
        pageRect: { width: pageRect.width, height: pageRect.height },
        highlightRect: { 
          width: highlightRect.width, 
          height: highlightRect.height,
          left: relativeX,
          top: relativeY
        }
      });
      
      return [x0Norm, y0Norm, x1Norm, y1Norm];
    } catch (e) {
      console.warn("Failed to convert highlight to bbox:", e);
      return null;
    }
  };

  const waitForFirstHighlightAndCenter = async (
    viewerContainer: HTMLElement,
    timeoutMs = 3000
  ) => {
    const findAndCenter = () => {
      const highlight =
        viewerContainer.querySelector<HTMLElement>(".highlight.selected") ||
        viewerContainer.querySelector<HTMLElement>(".highlight");
        
      if (!highlight) return false;
      
      // Find the parent page element
      const pageEl = highlight.closest<HTMLElement>(".page");
      const canvas = pageEl?.querySelector<HTMLCanvasElement>("canvas");
      
      if (pageEl && canvas) {
        // Convert highlight to normalized bbox and use same centering as OCR
        const bbox = convertHighlightToNormalizedBBox(highlight, pageEl);
        if (bbox) {
          scrollContainerToBBox(viewerContainer, pageEl, canvas, bbox);
          return true;
        }
      }
      
      // Fallback to scrollIntoView if bbox conversion fails
      highlight.scrollIntoView({ block: "center", inline: "nearest" });
      return true;
    };

    const already = findAndCenter();
    if (already) return true;

    return new Promise<boolean>((resolve) => {
      const obs = new MutationObserver(() => {
        if (findAndCenter()) {
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

    // 🎯 CONSTRAIN SEARCH TO PRECISE PAGE ± 1 PAGES ONLY
    if (precisePage && precisePage >= 1 && precisePage <= np) {
      // Limit search to just the precise page ± 1 pages instead of entire document
      if (precisePage - 1 >= 1) order.push(precisePage - 1);
      order.push(precisePage);
      if (precisePage + 1 <= np) order.push(precisePage + 1);

      console.log(`🎯 Fuzzy search constrained to pages: ${order.join(', ')} (from precise_page hint: ${precisePage})`);
    } else {
      // Fallback: no precise page available, search main pages with reduced priority
      // Still limited compared to full document search
      for (let d = 0; d <= Math.min(2, np - 1); d++) {
        if (1 + d <= np) order.push(1 + d);
      }
      console.log(`📄 Fuzzy search fallback - no precise page hint, limited to pages: ${order.join(', ')}`);
    }

    let best: { pageNum: number; score: number; snippet: string } | null = null;

    for (const p of order) {
      const res = await fuzzyScanPage(pdfDoc, p, needle);
      if (!res) continue;
      if (!best || res.score > best.score) {
        best = res;
        if (best.score >= 0.92) break;  // Still allow early exit for very good matches
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
    if (containerRef.current) {
      removeAllOverlayCanvases(containerRef.current);
      containerRef.current.innerHTML = "";
    }
  };

  // Fetch bbox data when component mounts
  useEffect(() => {
    const fetchBboxData = async () => {
      try {
        const bboxUrl =
          reportType === "saved" && reportId
            ? `/agents/reports/saved/${reportId}/documents/${quote.document_id}/bboxes`
            : `/agents/documents/${quote.document_id}/bboxes`;

        const response = await api(bboxUrl, {
          method: "GET",
        });

        if (response.ok) {
          const data = await response.json();
          setBboxData(data as DocumentBoundingBoxes);
          setHasBboxSupport(true);
        }
      } catch (error: unknown) {
        // 404 means document doesn't have bboxes (native PDF), not an error
        const errorMessage = error instanceof Error ? error.message : String(error);
        if (!errorMessage.includes("404")) {
          console.warn("Failed to fetch bbox data:", error);
        }
        setBboxData(null);
        setHasBboxSupport(false);
      }
    };

    fetchBboxData();
  }, [quote.document_id, reportType, reportId]);

  // Helper to render bbox highlights on a page
  const renderBboxHighlights = (pageNumber: number, wordSpans: WordSpan[]) => {
    if (!containerRef.current) return;

    // Find the page element
    const pageElements = containerRef.current.querySelectorAll<HTMLElement>(".page");
    let targetPage: HTMLElement | null = null;

    for (const pageEl of pageElements) {
      const pageNumAttr = pageEl.getAttribute("data-page-number");
      if (pageNumAttr && parseInt(pageNumAttr) === pageNumber) {
        targetPage = pageEl;
        break;
      }
    }

    if (!targetPage) {
      console.warn(`Page ${pageNumber} not found for bbox rendering`);
      return;
    }

    // Wait for page to be fully rendered
    const checkRendered = () => {
      const canvas = targetPage!.querySelector<HTMLCanvasElement>("canvas");
      if (!canvas || canvas.width === 0) {
        // Page not fully rendered yet, try again soon
        setTimeout(checkRendered, 100);
        return;
      }

      // Create overlay canvas and draw bboxes
      const overlayCanvas = createOverlayCanvas(targetPage!, pageNumber);
      const viewport = getPageViewport(targetPage!);

      if (viewport) {
        drawBoundingBoxes(overlayCanvas, wordSpans, viewport);
      }
    };

    checkRendered();
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

          // Check if quote has bbox data (OCR documents)
          const hasBboxes = quote.has_bounding_boxes && quote.word_spans && quote.word_spans.length > 0;

          if (hasBboxes && quote.word_spans) {
            // Use bbox rendering for OCR documents
            console.log("Using bbox highlighting for OCR document");

            // Group word spans by page
            const spansByPage = new Map<number, WordSpan[]>();
            for (const span of quote.word_spans) {
              const spans = spansByPage.get(span.page) || [];
              spans.push(span);
              spansByPage.set(span.page, spans);
            }

            // Navigate to first page with bboxes
            const firstPage = Math.min(...Array.from(spansByPage.keys()));
            if (firstPage >= 1 && firstPage <= pdfDoc.numPages) {
              viewer.currentPageNumber = firstPage;

              // Wait for page to render, then draw bboxes
              await new Promise((r) => setTimeout(r, 500));

              // Render bboxes for each page
              for (const [pageNum, spans] of spansByPage.entries()) {
                renderBboxHighlights(pageNum, spans);
              }

              // Scroll to first bbox highlight (not just the page)
              await new Promise((r) => setTimeout(r, 300));
              const firstPageEl = container.querySelector<HTMLElement>(
                `.page[data-page-number="${firstPage}"]`
              );
              const canvas = firstPageEl?.querySelector<HTMLCanvasElement>("canvas");
              
              if (firstPageEl && canvas && quote.word_spans && quote.word_spans.length > 0) {
                const firstBbox = quote.word_spans[0].bbox;
                scrollContainerToBBox(container, firstPageEl, canvas, firstBbox);
                centered = true;
              } else if (firstPageEl) {
                // Fallback to page centering if something went wrong
                firstPageEl.scrollIntoView({ block: "center", inline: "nearest" });
                centered = true;
              }
            }
          } else {
            // Fall back to text-based highlighting for native PDFs
            console.log("Using text-based highlighting for native PDF");

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
    const container = containerRef.current;
    if (!container) return;

    // Check if this is an OCR document with bboxes
    if (quote.has_bounding_boxes && quote.word_spans && quote.word_spans.length > 0) {
      // OCR document: scroll to first bbox
      const firstSpan = quote.word_spans[0];
      const pageEl = container.querySelector<HTMLElement>(
        `.page[data-page-number="${firstSpan.page}"]`
      );
      const canvas = pageEl?.querySelector<HTMLCanvasElement>("canvas");
      
      if (pageEl && canvas) {
        scrollContainerToBBox(container, pageEl, canvas, firstSpan.bbox);
      }
    } else {
      // Text-based PDF: find next highlight and center using same logic as OCR
      const bus = eventBusRef.current;
      if (bus && quoteTextRaw) {
        bus.dispatch("findagain", {
          type: "findagain",
          findPrevious: false,
          highlightAll: true,
          phraseSearch: true,
        } as any);
        setTimeout(() => {
          const highlight =
            container.querySelector<HTMLElement>(".highlight.selected") ||
            container.querySelector<HTMLElement>(".highlight");
            
          if (!highlight) {
            console.warn("[PDF] Jump requested but no highlight present.");
            return;
          }
          
          // Convert highlight to normalized bbox and use same centering as OCR
          const pageEl = highlight.closest<HTMLElement>(".page");
          const canvas = pageEl?.querySelector<HTMLCanvasElement>("canvas");
          
          if (pageEl && canvas) {
            const bbox = convertHighlightToNormalizedBBox(highlight, pageEl);
            if (bbox) {
              scrollContainerToBBox(container, pageEl, canvas, bbox);
            } else {
              // Fallback to scrollIntoView if conversion fails
              highlight.scrollIntoView({ block: "center", inline: "nearest" });
            }
          } else {
            // Fallback to scrollIntoView if page elements not found
            highlight.scrollIntoView({ block: "center", inline: "nearest" });
          }
        }, 120);
      }
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
