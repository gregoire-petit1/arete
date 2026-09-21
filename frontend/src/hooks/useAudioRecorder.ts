import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Records a short voice clip with MediaRecorder.
 *
 * Every piece of live state lives in a ref: a cleanup that closed over stale
 * state would leave the microphone stream open, and the browser keeps showing
 * the recording indicator until every track is stopped.
 */

export type RecorderStatus = 'idle' | 'requesting' | 'recording' | 'stopping';

export type RecorderReason =
  | 'unsupported'
  | 'insecure-context'
  | 'permission-denied'
  | 'no-device'
  | 'device-busy'
  | 'too-short'
  | 'too-large'
  | 'capture-failed';

export interface AudioClip {
  blob: Blob;
  mimeType: string;
  extension: string;
  durationMs: number;
}

export interface RecorderError {
  reason: RecorderReason;
  message: string;
}

interface Options {
  onClip: (clip: AudioClip) => void;
  maxDurationMs?: number;
  minDurationMs?: number;
  maxBytes?: number;
}

const DEFAULTS = {
  maxDurationMs: 120_000,
  minDurationMs: 1_000,
  maxBytes: 8 * 1024 * 1024,
};

/** Chrome and Firefox give webm/opus, Safari gives mp4/AAC. */
const CANDIDATE_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4;codecs=mp4a.40.2',
  'audio/mp4',
  'audio/ogg;codecs=opus',
];

const EXTENSIONS: Record<string, string> = {
  'audio/webm': 'webm',
  'audio/mp4': 'mp4',
  'audio/x-m4a': 'm4a',
  'audio/mpeg': 'mp3',
  'audio/ogg': 'ogg',
  'audio/wav': 'wav',
};

const MESSAGES: Record<RecorderReason, string> = {
  unsupported: "Ce navigateur ne sait pas enregistrer l'audio.",
  'insecure-context': 'Dictée indisponible : la connexion doit être sécurisée (HTTPS).',
  'permission-denied': 'Micro refusé. Autorise le micro dans les réglages du navigateur.',
  'no-device': 'Aucun micro détecté.',
  'device-busy': 'Micro indisponible, une autre application l’utilise.',
  'too-short': 'Enregistrement trop court.',
  'too-large': 'Enregistrement trop volumineux, raccourcis la dictée.',
  'capture-failed': "Impossible de démarrer l'enregistrement.",
};

function pickMimeType(): string {
  if (typeof MediaRecorder === 'undefined') return '';
  return CANDIDATE_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) ?? '';
}

/** The browser may ignore the requested type, so read back what it actually used. */
function extensionOf(mimeType: string): string {
  const base = mimeType.split(';')[0].trim().toLowerCase();
  return EXTENSIONS[base] ?? 'webm';
}

function reasonOf(error: unknown): RecorderReason {
  const name = error instanceof Error ? error.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'permission-denied';
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') return 'no-device';
  if (name === 'NotReadableError' || name === 'TrackStartError') return 'device-busy';
  return 'capture-failed';
}

export function useAudioRecorder({ onClip, ...limits }: Options) {
  const { maxDurationMs, minDurationMs, maxBytes } = { ...DEFAULTS, ...limits };

  const [status, setStatus] = useState<RecorderStatus>('idle');
  const [elapsedMs, setElapsedMs] = useState(0);
  const [error, setError] = useState<RecorderError | null>(null);
  const [autoStopped, setAutoStopped] = useState(false);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const cancelledRef = useRef(false);
  const timerRef = useRef<number | null>(null);
  // Keep the latest callback without re-creating the recorder on every render.
  const onClipRef = useRef(onClip);
  useEffect(() => {
    onClipRef.current = onClip;
  }, [onClip]);

  const isSupported =
    typeof window !== 'undefined' &&
    typeof MediaRecorder !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia);

  /** Idempotent: called on stop, cancel, error and unmount. */
  const release = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
  }, []);

  const fail = useCallback(
    (reason: RecorderReason) => {
      release();
      setStatus('idle');
      setElapsedMs(0);
      setError({ reason, message: MESSAGES[reason] });
    },
    [release]
  );

  const stop = useCallback(() => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      release();
      setStatus('idle');
      return;
    }
    setStatus('stopping');
    recorder.stop();
  }, [release]);

  const cancel = useCallback(() => {
    cancelledRef.current = true;
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    } else {
      release();
    }
    setStatus('idle');
    setElapsedMs(0);
  }, [release]);

  const start = useCallback(async () => {
    if (status !== 'idle') return;
    setError(null);
    setAutoStopped(false);

    if (!window.isSecureContext) return fail('insecure-context');
    if (!isSupported) return fail('unsupported');

    setStatus('requesting');
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch (err) {
      return fail(reasonOf(err));
    }

    let recorder: MediaRecorder;
    try {
      const mimeType = pickMimeType();
      recorder = new MediaRecorder(stream, {
        ...(mimeType ? { mimeType } : {}),
        audioBitsPerSecond: 32_000,
      });
    } catch {
      stream.getTracks().forEach((track) => track.stop());
      return fail('capture-failed');
    }

    streamRef.current = stream;
    recorderRef.current = recorder;
    chunksRef.current = [];
    cancelledRef.current = false;
    startedAtRef.current = performance.now();

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      const durationMs = performance.now() - startedAtRef.current;
      const mimeType = recorder.mimeType || 'audio/webm';
      const blob = new Blob(chunksRef.current, { type: mimeType });
      chunksRef.current = [];
      release();
      setStatus('idle');
      setElapsedMs(0);

      if (cancelledRef.current) return;
      if (durationMs < minDurationMs) return fail('too-short');
      if (blob.size > maxBytes) return fail('too-large');
      onClipRef.current({
        blob,
        mimeType,
        extension: extensionOf(mimeType),
        durationMs,
      });
    };

    recorder.start(1_000); // chunks as we go, so size is known before the end
    setStatus('recording');
    timerRef.current = window.setInterval(() => {
      const elapsed = performance.now() - startedAtRef.current;
      setElapsedMs(elapsed);
      if (elapsed >= maxDurationMs) {
        setAutoStopped(true);
        stop();
      }
    }, 250);
  }, [fail, isSupported, maxBytes, maxDurationMs, minDurationMs, release, status, stop]);

  // Backstop: a modal closing mid-recording must not leave the mic live.
  useEffect(() => release, [release]);

  return {
    status,
    isRecording: status === 'recording',
    isSupported,
    isSecure: typeof window === 'undefined' || window.isSecureContext,
    elapsedMs,
    autoStopped,
    error,
    start,
    stop,
    cancel,
    clearError: () => setError(null),
  };
}
