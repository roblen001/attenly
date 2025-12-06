import type { WordSpan } from "../types";

/**
 * Simple viewport interface for coordinate transformation
 * Represents the dimensions of a PDF page in pixels
 */
export interface PageViewport {
  width: number;
  height: number;
}

/**
 * Creates a transparent canvas overlay on a PDF page for bbox highlighting
 */
export function createOverlayCanvas(
  pageElement: HTMLElement,
  pageNumber: number
): HTMLCanvasElement {
  // Check if canvas already exists
  let canvas = pageElement.querySelector<HTMLCanvasElement>(
    `.bbox-overlay-canvas[data-page="${pageNumber}"]`
  );

  if (canvas) {
    return canvas;
  }

  // Create new canvas
  canvas = document.createElement("canvas");
  canvas.className = "bbox-overlay-canvas";
  canvas.dataset.page = String(pageNumber);
  canvas.style.position = "absolute";
  canvas.style.top = "0";
  canvas.style.left = "0";
  canvas.style.pointerEvents = "none";
  canvas.style.zIndex = "2"; // Above PDF content, below text layer

  // Find the canvas layer (where PDF renders) to match dimensions
  const pdfCanvas = pageElement.querySelector<HTMLCanvasElement>("canvas");
  if (pdfCanvas) {
    canvas.width = pdfCanvas.width;
    canvas.height = pdfCanvas.height;
    canvas.style.width = pdfCanvas.style.width;
    canvas.style.height = pdfCanvas.style.height;
  }

  // Insert canvas into page
  const canvasWrapper = pageElement.querySelector(".canvasWrapper");
  if (canvasWrapper) {
    canvasWrapper.appendChild(canvas);
  } else {
    pageElement.appendChild(canvas);
  }

  return canvas;
}

/**
 * Clears all highlights from a canvas overlay
 */
export function clearOverlayCanvas(canvas: HTMLCanvasElement): void {
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
}

/**
 * Unions adjacent bounding boxes for cleaner multi-word highlighting
 */
export function unionBoundingBoxes(wordSpans: WordSpan[]): Array<{
  bbox: [number, number, number, number];
  page: number;
}> {
  if (wordSpans.length === 0) return [];

  // Group by page
  const byPage = new Map<number, WordSpan[]>();
  for (const span of wordSpans) {
    const spans = byPage.get(span.page) || [];
    spans.push(span);
    byPage.set(span.page, spans);
  }

  const unions: Array<{ bbox: [number, number, number, number]; page: number }> = [];

  // For each page, union bboxes on the same line
  for (const [page, spans] of byPage.entries()) {
    // Sort by line_index, then word_index
    const sorted = [...spans].sort((a, b) => {
      const lineA = a.line_index ?? 0;
      const lineB = b.line_index ?? 0;
      if (lineA !== lineB) return lineA - lineB;
      return (a.word_index ?? 0) - (b.word_index ?? 0);
    });

    let currentUnion: [number, number, number, number] | null = null;
    let currentLine: number | null = null;

    for (const span of sorted) {
      const line = span.line_index ?? 0;

      if (currentLine === null || line !== currentLine) {
        // New line - save previous union if exists
        if (currentUnion) {
          unions.push({ bbox: currentUnion, page });
        }
        // Start new union
        currentUnion = [...span.bbox] as [number, number, number, number];
        currentLine = line;
      } else {
        // Same line - expand union
        if (currentUnion) {
          currentUnion[0] = Math.min(currentUnion[0], span.bbox[0]); // x0
          currentUnion[1] = Math.min(currentUnion[1], span.bbox[1]); // y0
          currentUnion[2] = Math.max(currentUnion[2], span.bbox[2]); // x1
          currentUnion[3] = Math.max(currentUnion[3], span.bbox[3]); // y1
        }
      }
    }

    // Save final union for this page
    if (currentUnion) {
      unions.push({ bbox: currentUnion, page });
    }
  }

  return unions;
}

/**
 * Draws bounding box rectangles on the canvas overlay
 * @param canvas The overlay canvas element
 * @param wordSpans Array of word spans with normalized bbox coordinates
 * @param viewport PDF.js viewport for coordinate transformation
 */
export function drawBoundingBoxes(
  canvas: HTMLCanvasElement,
  wordSpans: WordSpan[],
  viewport: PageViewport
): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  // Clear previous highlights
  clearOverlayCanvas(canvas);

  // Union adjacent boxes for cleaner highlighting
  const unions = unionBoundingBoxes(wordSpans);

  // Draw each unioned bbox
  for (const { bbox } of unions) {
    // Convert normalized [0,1] coordinates to viewport pixel coordinates
    const [x0Norm, y0Norm, x1Norm, y1Norm] = bbox;

    // Scale to viewport dimensions
    const x0 = x0Norm * viewport.width;
    const y0 = y0Norm * viewport.height;
    const x1 = x1Norm * viewport.width;
    const y1 = y1Norm * viewport.height;

    const width = x1 - x0;
    const height = y1 - y0;

    // Draw semi-transparent yellow highlight
    ctx.fillStyle = "rgba(255, 235, 59, 0.3)"; // Yellow with 30% opacity
    ctx.fillRect(x0, y0, width, height);
  }
}

/**
 * Removes all bbox overlay canvases from a container
 */
export function removeAllOverlayCanvases(container: HTMLElement): void {
  const canvases = container.querySelectorAll<HTMLCanvasElement>(
    ".bbox-overlay-canvas"
  );
  canvases.forEach((canvas) => canvas.remove());
}

/**
 * Gets the viewport for a specific PDF page
 * This is a helper to extract viewport from PDF.js rendered page
 */
export function getPageViewport(pageElement: HTMLElement): PageViewport | null {
  // The viewport info is stored in the page's dataset or can be calculated from canvas
  const pdfCanvas = pageElement.querySelector<HTMLCanvasElement>("canvas");
  if (!pdfCanvas) return null;

  // Simple viewport object with width/height
  // PDF.js actual viewport has more methods, but we only need dimensions
  return {
    width: pdfCanvas.width,
    height: pdfCanvas.height,
  };
}
