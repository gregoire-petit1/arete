import type { Extraction, SourceBlock } from './documents';
import { createWorker, OEM, type Worker } from 'tesseract.js';
import { getDocument, GlobalWorkerOptions, OPS } from 'pdfjs-dist';
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

GlobalWorkerOptions.workerSrc = pdfWorker;
const MAX_PAGES = 100;
const MAX_PIXELS = 25_000_000;
const MAX_EXTRACTION_BYTES = 2 * 1024 * 1024;
const PAGE_TIMEOUT = 60_000;
const DOCUMENT_TIMEOUT = 600_000;

async function bounded<T>(work: Promise<T>, signal: AbortSignal, ms = PAGE_TIMEOUT): Promise<T> {
  signal.throwIfAborted();
  let abort: () => void = () => {};
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([work, new Promise<never>((_, reject) => {
      abort = () => reject(signal.reason ?? new Error('Traitement annulé.'));
      signal.addEventListener('abort', abort, { once: true });
      timer = setTimeout(() => reject(new Error('Traitement trop long. Sépare le document ou utilise une image plus petite.')), ms);
    })]);
  } finally {
    signal.removeEventListener('abort', abort);
    clearTimeout(timer);
  }
}

export async function extractDocument(file: File, externalSignal: AbortSignal, progress: (message: string) => void): Promise<Extraction> {
  const lifetime = new AbortController();
  const signal = AbortSignal.any([externalSignal, lifetime.signal, AbortSignal.timeout(DOCUMENT_TIMEOUT)]);
  const result: Extraction = { blocks: [], warnings: [] };
  let worker: Worker | null = null;
  let extractionBytes = 0;
  const add = (block: SourceBlock) => {
    extractionBytes += new TextEncoder().encode(JSON.stringify(block)).length;
    if (extractionBytes > MAX_EXTRACTION_BYTES - 4096) throw new Error('Extraction trop volumineuse (2 Mio). Sépare le document.');
    result.blocks.push(block);
  };
  const ocr = async (canvas: HTMLCanvasElement, page: number, signal: AbortSignal) => {
    if (!worker) {
      progress('Chargement de la reconnaissance de texte…');
      worker = await bounded(createWorker(['fra', 'eng'], OEM.LSTM_ONLY, { workerPath: '/ocr/worker.min.js', corePath: '/ocr', langPath: '/ocr', logger: event => { if (event.status === 'recognizing text') progress(`Page ${page} · reconnaissance ${Math.round(event.progress * 100)} %`); } }).then(async value => {
        if (signal.aborted) { await value.terminate(); signal.throwIfAborted(); }
        return value;
      }), signal);
    }
    const { data } = await bounded((worker as Worker).recognize(canvas, { rotateAuto: true }, { text: true, blocks: true }), signal);
    let count = 0;
    for (const block of data.blocks ?? []) {
      for (const paragraph of block.paragraphs) {
        for (const line of paragraph.lines) {
          if (++count > 5000) throw new Error('Plus de 5 000 lignes sur une page.');
          add({ locator: `page ${page}, ligne ${count}`, text: line.text, method: 'ocr', confidence: line.confidence, box: [line.bbox.x0, line.bbox.y0, line.bbox.x1, line.bbox.y1] });
        }
      }
    }
    if (!count && data.text.trim()) add({ locator: `page ${page}`, text: data.text, method: 'ocr', confidence: data.confidence });
  };
  try {
    if (file.name.toLowerCase().endsWith('.pdf')) {
      const loading = getDocument({ data: new Uint8Array(await file.arrayBuffer()), useSystemFonts: true });
      loading.onPassword = () => { void loading.destroy(); };
      const abort = () => { void loading.destroy(); };
      signal.addEventListener('abort', abort, { once: true });
      try {
        const pdf = await bounded(loading.promise, signal);
        if (pdf.numPages > MAX_PAGES) throw new Error('Maximum 100 pages par PDF.');
        for (let number = 1; number <= pdf.numPages; number++) {
          const pageSignal = AbortSignal.any([signal, AbortSignal.timeout(PAGE_TIMEOUT)]);
          pageSignal.throwIfAborted();
          progress(`Lecture de la page ${number}/${pdf.numPages}…`);
          const page = await bounded(pdf.getPage(number), pageSignal);
          const text = await bounded(page.getTextContent(), pageSignal);
          const operators = await bounded(page.getOperatorList(), pageSignal);
          if (operators.fnArray.length > 100_000) throw new Error('Page PDF trop complexe.');
          const hasImages = operators.fnArray.some(op => [OPS.paintImageXObject, OPS.paintInlineImageXObject, OPS.paintImageXObjectRepeat].includes(op));
          const items = text.items.filter(item => 'str' in item);
          if (!hasImages && items.some(item => item.str.trim())) {
            if (items.length > 5000) throw new Error('Page trop dense (5 000 blocs maximum).');
            items.forEach((item, index) => add({ locator: `page ${number}, bloc ${index + 1}`, text: item.str, method: 'text', box: [item.transform[4], item.transform[5], item.width, item.height] }));
          } else {
            const viewport = page.getViewport({ scale: 2 });
            if (viewport.width * viewport.height > MAX_PIXELS) throw new Error('Page trop grande pour la reconnaissance.');
            const canvas = document.createElement('canvas');
            canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
            await bounded(page.render({ canvas, viewport }).promise, pageSignal);
            await ocr(canvas, number, pageSignal);
            canvas.width = 0; canvas.height = 0;
          }
          page.cleanup();
        }
      } finally {
        signal.removeEventListener('abort', abort);
        await loading.destroy();
      }
    } else {
      const pageSignal = AbortSignal.any([signal, AbortSignal.timeout(PAGE_TIMEOUT)]);
      const bitmap = await bounded(createImageBitmap(file), pageSignal);
      try {
        if (bitmap.width * bitmap.height > MAX_PIXELS) throw new Error('Maximum 25 mégapixels par image.');
        const canvas = document.createElement('canvas');
        canvas.width = bitmap.width; canvas.height = bitmap.height;
        canvas.getContext('2d')!.drawImage(bitmap, 0, 0);
        await ocr(canvas, 1, pageSignal);
        canvas.width = 0; canvas.height = 0;
      } finally { bitmap.close(); }
    }
    if (!result.blocks.some(block => block.text.trim())) throw new Error('Aucun texte lisible. Utilise une image plus nette.');
    if (result.blocks.some(block => block.method === 'ocr')) result.warnings.push('Texte reconnu automatiquement : vérifie les dates, chiffres et unités dans l’original.');
    return result;
  } finally {
    lifetime.abort();
    if (worker) await (worker as Worker).terminate();
  }
}
