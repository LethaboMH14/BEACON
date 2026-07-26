/**
 * Vision Lens — plug in a video, watch the AI analyse it in real time.
 *
 * WHAT IS REAL HERE
 * Every detection on this screen is a live Roboflow model call via the server's
 * vision job pipeline (POST /v1/vision/jobs). The frame events stream over the
 * ops WebSocket (/ws/ops) as they happen — one frame analysed, one row drawn,
 * level climbing or not. Nothing is pre-recorded or mocked.
 *
 * Three detectors run on every frame, concurrently:
 *   WEAPON  — Roboflow weapons-detection-xvtjj/1, trained on firearms
 *   PLATE   — Roboflow license-plate-recognition-rxg4e/11 + OCR
 *   FACE    — from the same sightings pipeline (face kind)
 *
 * THE DECISION MACHINE
 * Raw detections alone are not a decision. The situation object tells you what
 * everything together means. It has four levels:
 *   QUIET      → nothing above threshold
 *   NOTICE     → something seen, not worth interrupting a person
 *   CANDIDATE  → machine ceiling, a human should look now
 *   ESCALATED  → a named human reviewed it and escalated; never set by the model
 *
 * A weapon must appear in at least 2 sampled frames (or hit 80%+ confidence in
 * one) before the machine even reaches CANDIDATE. One frame is not enough.
 * Plates and faces never raise the level — they are context that makes a
 * weapon sighting actionable (who to look for), not evidence of a crime.
 *
 * THE DISPLAY IS THE THINKING
 * Each frame row shows what the model detected and at what confidence. The
 * confidence bar is the probability the model assigned; the level is a
 * function of confidence × persistence, not confidence alone. When the level
 * climbs you can read the exact reason in the situation panel: "pistol seen in
 * 3 of 4 frames at up to 67% confidence" is diagnosable. "Elevated" is not.
 *
 * WHAT IS NOT REAL
 * Facial recognition (matching against a watch-list) is not wired up — the
 * detector identifies that a face is present, not whose face it is. That is an
 * honest description of what the model does.
 */
import { useEffect, useRef, useState } from 'react';
import { colors } from '../../theme/tokens';
import { Button, Card, Chip, MethodNote, Screen, ScreenHeader, radii } from '../ui';
import { apiUrl, wsUrl } from '../../api/base';

// ── types mirroring server/src/vision/jobs.py ─────────────────────────────

interface Detection {
  kind: string;        // "weapon" | "plate" | "face"
  label: string;
  confidence: number;
  bbox?: { x: number; y: number; w: number; h: number } | null;
  ocr_text?: string | null;
}

interface FrameRecord {
  frame_index: number;
  t: number;           // seconds into clip
  detections: Detection[];
  detector_ms: number;
  clahe?: { applied: boolean; reason: string };
  errors?: string[];
}

interface SituationCounts {
  frames: number;
  weapon_frames: number;
  weapon_peak_confidence: number;
  weapon_labels: Record<string, number>;
  plate_frames: number;
  plates_read: string[];
  face_frames: number;
}

interface Situation {
  source_id: string;
  level: number;        // 0=QUIET 1=NOTICE 2=CANDIDATE 3=ESCALATED
  level_name: string;
  level_label: string;
  reason: string;
  recommendation: string;
  machine_ceiling_reached: boolean;
  evidence: { code: string; text: string; note: string }[];
  counts: SituationCounts;
  first_weapon_at_s: number | null;
}

type JobStatus = 'idle' | 'uploading' | 'running' | 'done' | 'failed' | 'cancelled';

// ── helpers ───────────────────────────────────────────────────────────────

const LEVEL_COLOR: Record<number, string> = {
  0: colors.textLo,
  1: colors.watch,
  2: colors.critical,
  3: colors.critical,
};

const LEVEL_LABEL: Record<number, string> = {
  0: 'CLEAR',
  1: 'NOTICE',
  2: 'CANDIDATE',
  3: 'ESCALATED',
};

const KIND_COLOR: Record<string, string> = {
  weapon: colors.critical,
  plate:  colors.discovery,
  face:   colors.beacon,
};

function kindColor(kind: string): string {
  return KIND_COLOR[kind] ?? colors.textMid;
}

function fmtPct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

function fmtT(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}

// ── component ─────────────────────────────────────────────────────────────

export default function VisionLens() {
  const [, setJobId]                  = useState<string | null>(null);
  const [status,      setStatus]      = useState<JobStatus>('idle');
  const [progress,    setProgress]    = useState(0);           // 0..1
  const [frames,      setFrames]      = useState<FrameRecord[]>([]);
  const [situation,   setSituation]   = useState<Situation | null>(null);
  const [uploadErr,   setUploadErr]   = useState<string | null>(null);
  const [fileName,    setFileName]    = useState<string | null>(null);
  const [estimatedS,  setEstimatedS]  = useState<number | null>(null);
  const [backendNote, setBackendNote] = useState<string>('');

  const fileRef      = useRef<HTMLInputElement>(null);
  const wsRef        = useRef<WebSocket | null>(null);
  const jobIdRef     = useRef<string | null>(null);   // for the WS message filter
  const frameListRef = useRef<HTMLDivElement>(null);

  // ── WS — connect once on mount, stay alive across jobs ───────────────────
  // Connecting BEFORE the upload eliminates the race where the server starts
  // processing and emitting vision.frame events while the WS handshake is
  // still in flight.

  useEffect(() => {
    const ws = new WebSocket(wsUrl('/ws/ops'));
    wsRef.current = ws;

    ws.onmessage = (e) => {
      let msg: { event: string; data: unknown };
      try { msg = JSON.parse(e.data); } catch { return; }

      const { event, data } = msg as { event: string; data: Record<string, unknown> };
      // Filter to the current job only; ignore unrelated ops events.
      if ((data as { job_id?: string }).job_id !== jobIdRef.current) return;

      if (event === 'vision.frame') {
        const d = data as { frame: FrameRecord; progress: number; situation: Situation };
        setFrames((prev) => [...prev, d.frame]);
        setProgress(d.progress ?? 0);
        setSituation(d.situation);
        setTimeout(() => {
          if (frameListRef.current) {
            frameListRef.current.scrollTop = frameListRef.current.scrollHeight;
          }
        }, 0);
      } else if (event === 'vision.decision' || event === 'vision.failed' || event === 'vision.cancelled') {
        const d = data as { situation?: Situation };
        if (d.situation) setSituation(d.situation);
        setStatus(
          event === 'vision.decision' ? 'done'
          : event === 'vision.failed' ? 'failed'
          : 'cancelled'
        );
        setProgress(1);
      }
    };

    ws.onerror = () => {
      // Non-fatal: the upload will still work; we just won't stream frames.
      // The server keeps the job record so the result is retrievable via GET.
    };

    return () => ws.close();
  }, []);

  // ── upload & kick off ────────────────────────────────────────────────────

  async function handleFile(file: File) {
    setUploadErr(null);
    setFrames([]);
    setSituation(null);
    setProgress(0);
    setFileName(file.name);
    setStatus('uploading');
    setJobId(null);
    jobIdRef.current = null;

    const form = new FormData();
    form.append('file', file);
    form.append('sample_fps', '1');

    try {
      const res = await fetch(apiUrl('/v1/vision/jobs'), { method: 'POST', body: form });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`${res.status}: ${txt}`);
      }
      const job = (await res.json()) as {
        job_id: string; estimated_seconds: number | null; note: string; backend: string;
      };
      // Set the ref first so the already-running WS handler starts accepting
      // events for this job before we update React state.
      jobIdRef.current = job.job_id;
      setJobId(job.job_id);
      setEstimatedS(job.estimated_seconds);
      setBackendNote(job.backend === 'local' ? 'Local model (no cloud)' : 'Roboflow hosted');
      setStatus('running');
    } catch (err) {
      setUploadErr(err instanceof Error ? err.message : 'Upload failed');
      setStatus('failed');
    }
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = '';
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  // ── layout ───────────────────────────────────────────────────────────────

  const hasWeapon   = (situation?.counts.weapon_frames ?? 0) > 0;
  const hasPlate    = (situation?.counts.plate_frames ?? 0) > 0;
  const hasFace     = (situation?.counts.face_frames ?? 0) > 0;
  const levelNum    = situation?.level ?? 0;
  const levelColor  = LEVEL_COLOR[levelNum] ?? colors.textMid;

  return (
    <Screen>
      <ScreenHeader
        dark
        title="Vision lens"
        subtitle="Live gun · plate · face detection"
        right={status === 'running' ? <Chip tone="live" dark>Analysing</Chip> : <Chip tone="neutral" dark>{status === 'done' ? 'Done' : 'Ready'}</Chip>}
      />

      {/* ── drop zone / file picker ── */}
      {status === 'idle' || status === 'failed' ? (
        <Card dark style={{ padding: 0, marginBottom: 14, overflow: 'hidden' }}>
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            style={{
              padding: 32, textAlign: 'center', cursor: 'pointer',
              borderRadius: radii.card,
              border: `2px dashed ${colors.lineDark}`,
              background: colors.bg800,
              transition: 'background 0.15s',
            }}
          >
            <div style={{ fontSize: 28, marginBottom: 8 }}>🎬</div>
            <div style={{ fontWeight: 700, fontSize: 14, color: colors.textHi, marginBottom: 4 }}>
              Drop a video or tap to pick
            </div>
            <div style={{ fontSize: 12, color: colors.textMid }}>
              MP4 · MOV · AVI · MKV · WebM · max 60 MB
            </div>
            {uploadErr && (
              <div style={{ marginTop: 12, fontSize: 12, color: colors.critical }}>
                {uploadErr}
              </div>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept="video/mp4,video/quicktime,video/avi,video/x-msvideo,video/x-matroska,video/webm"
            style={{ display: 'none' }}
            onChange={onFileChange}
          />
        </Card>
      ) : null}

      {/* ── uploading spinner ── */}
      {status === 'uploading' && (
        <Card dark style={{ padding: 18, marginBottom: 14, textAlign: 'center' }}>
          <div style={{ fontSize: 13, color: colors.textMid }}>Uploading {fileName}…</div>
        </Card>
      )}

      {/* ── running / done ── */}
      {(status === 'running' || status === 'done' || status === 'cancelled') && (
        <>
          {/* Progress bar + meta */}
          <Card dark style={{ padding: 14, marginBottom: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontSize: 12, color: colors.textMid }}>
              <span style={{ fontWeight: 600, color: colors.textHi, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '60%' }}>
                {fileName}
              </span>
              <span className="tabular-nums">
                {frames.length} frame{frames.length !== 1 ? 's' : ''}
                {estimatedS ? ` · ~${estimatedS}s` : ''}
              </span>
            </div>
            <div style={{ height: 6, borderRadius: 3, background: colors.bg700, overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 3,
                background: status === 'done' ? colors.safe : colors.discovery,
                width: `${Math.round(progress * 100)}%`,
                transition: 'width 0.3s ease',
              }} />
            </div>
            <div style={{ marginTop: 6, fontSize: 11, color: colors.textLo, display: 'flex', justifyContent: 'space-between' }}>
              <span>{backendNote}</span>
              <span>{Math.round(progress * 100)}%{status === 'done' ? ' · complete' : ''}</span>
            </div>
          </Card>

          {/* SITUATION — the decision machine's current read */}
          <Card
            dark
            style={{ padding: 16, marginBottom: 14 }}
            accent={levelNum >= 2 ? `color-mix(in srgb, ${colors.critical} 30%, transparent)` : undefined}
          >
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.8, color: colors.textLo, marginBottom: 8 }}>
              SITUATION · DECISION MACHINE
            </div>

            {/* Level meter — four bars */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 10 }}>
              {[0, 1, 2, 3].map((lvl) => (
                <div key={lvl} style={{
                  flex: 1, height: 6, borderRadius: 3,
                  background: levelNum >= lvl ? levelColor : colors.bg700,
                  transition: 'background 0.4s ease',
                }} />
              ))}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 16, fontWeight: 800, color: levelColor }}>
                {LEVEL_LABEL[levelNum] ?? '—'}
              </span>
              {situation?.machine_ceiling_reached && (
                <Chip tone="critical">Needs human review</Chip>
              )}
            </div>

            <div style={{ fontSize: 12.5, color: colors.textHi, marginBottom: 8, lineHeight: 1.45 }}>
              {situation?.reason ?? 'Waiting for first frame…'}
            </div>

            {/* Detection summary pills */}
            {situation && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                {hasWeapon && (
                  <span style={{ fontSize: 11, fontWeight: 600, color: colors.critical, background: `color-mix(in srgb, ${colors.critical} 12%, transparent)`, padding: '3px 8px', borderRadius: radii.chip }}>
                    WEAPON ×{situation.counts.weapon_frames} · peak {fmtPct(situation.counts.weapon_peak_confidence)}
                  </span>
                )}
                {hasPlate && (
                  <span style={{ fontSize: 11, fontWeight: 600, color: colors.discovery, background: `color-mix(in srgb, ${colors.discovery} 12%, transparent)`, padding: '3px 8px', borderRadius: radii.chip }}>
                    PLATE ×{situation.counts.plate_frames}
                    {situation.counts.plates_read.length > 0 ? ` · ${situation.counts.plates_read.join(', ')}` : ' (unreadable)'}
                  </span>
                )}
                {hasFace && (
                  <span style={{ fontSize: 11, fontWeight: 600, color: colors.beacon, background: `color-mix(in srgb, ${colors.beacon} 12%, transparent)`, padding: '3px 8px', borderRadius: radii.chip }}>
                    FACE ×{situation.counts.face_frames}
                  </span>
                )}
                {!hasWeapon && !hasPlate && !hasFace && frames.length > 0 && (
                  <span style={{ fontSize: 11, color: colors.textLo }}>Nothing detected in {frames.length} frame{frames.length !== 1 ? 's' : ''}</span>
                )}
              </div>
            )}

            {/* Evidence items — the reasoning trail */}
            {situation?.evidence.map((ev) => (
              <div key={ev.code} style={{ marginTop: 6, padding: '6px 10px', background: colors.bg50, borderRadius: radii.chip }}>
                <div style={{ fontSize: 11.5, color: colors.textHi, fontWeight: 600 }}>{ev.text}</div>
                {ev.note && <div style={{ fontSize: 10.5, color: colors.textLo, marginTop: 2 }}>{ev.note}</div>}
              </div>
            ))}

            {situation && (
              <div style={{ marginTop: 10, fontSize: 11.5, color: levelNum >= 2 ? colors.critical : colors.textMid, fontWeight: levelNum >= 2 ? 700 : 400 }}>
                → {situation.recommendation}
              </div>
            )}
          </Card>

          {/* FRAME LOG — what the model actually saw, frame by frame */}
          <Card dark style={{ padding: 0, marginBottom: 14, overflow: 'hidden' }}>
            <div style={{ padding: '12px 14px 8px', fontSize: 10, fontWeight: 700, letterSpacing: 0.8, color: colors.textLo, borderBottom: `1px solid ${colors.lineDark}` }}>
              FRAME LOG · WHAT THE MODEL SAW
            </div>
            <div
              ref={frameListRef}
              style={{ maxHeight: 280, overflowY: 'auto', padding: '4px 0' }}
            >
              {frames.length === 0 && (
                <div style={{ padding: 16, fontSize: 12, color: colors.textLo, textAlign: 'center' }}>
                  Waiting for first frame…
                </div>
              )}
              {frames.map((f) => (
                <FrameRow key={f.frame_index} frame={f} />
              ))}
            </div>
          </Card>

          {status === 'done' && (
            <Button
              dark
              variant="secondary"
              onClick={() => {
                setStatus('idle');
                setFrames([]);
                setSituation(null);
                setProgress(0);
                setFileName(null);
                setJobId(null);
              }}
            >
              Analyse another video
            </Button>
          )}
        </>
      )}

      <MethodNote dark>
        {status === 'idle' || status === 'failed'
          ? 'Weapon, plate and face detection run concurrently on each sampled frame at ~1 fps. The decision machine scores persistence — one frame is not enough to raise the level. Plates and faces never raise the level; only a weapon held across frames can.'
          : 'Each row is one sampled frame (~1/sec). Confidence is the model\'s probability; the level climbs only when a weapon persists or hits very high confidence in one frame. Plates and faces are context — they name a lead, not a threat.'}
      </MethodNote>
    </Screen>
  );
}

// ── FrameRow ──────────────────────────────────────────────────────────────

function FrameRow({ frame }: { frame: FrameRecord }) {
  const weapons  = frame.detections.filter((d) => d.kind === 'weapon');
  const plates   = frame.detections.filter((d) => d.kind === 'plate');
  const faces    = frame.detections.filter((d) => d.kind === 'face');
  const isEmpty  = frame.detections.length === 0;
  const hasAlarm = weapons.length > 0;

  return (
    <div style={{
      padding: '7px 14px',
      borderBottom: `1px solid ${colors.bg50}`,
      background: hasAlarm ? `color-mix(in srgb, ${colors.critical} 6%, transparent)` : 'transparent',
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: isEmpty ? 0 : 4 }}>
        <span className="tabular-nums" style={{ fontSize: 10.5, color: colors.textLo, minWidth: 30 }}>
          {fmtT(frame.t)}
        </span>
        <span className="tabular-nums" style={{ fontSize: 10, color: colors.textLo }}>
          {frame.detector_ms.toFixed(0)}ms
        </span>
        {frame.clahe?.applied && (
          <span style={{ fontSize: 9.5, color: colors.watch, fontWeight: 600 }}>CLAHE</span>
        )}
        {isEmpty && (
          <span style={{ fontSize: 11, color: colors.textLo }}>nothing detected</span>
        )}
      </div>

      {weapons.map((d, i) => (
        <DetectionBar key={i} d={d} />
      ))}
      {plates.map((d, i) => (
        <DetectionBar key={i} d={d} />
      ))}
      {faces.map((d, i) => (
        <DetectionBar key={i} d={d} />
      ))}

      {frame.errors && frame.errors.length > 0 && (
        <div style={{ fontSize: 10, color: colors.watch, marginTop: 2 }}>
          ⚠ {frame.errors.join('; ')}
        </div>
      )}
    </div>
  );
}

function DetectionBar({ d }: { d: Detection }) {
  const color = kindColor(d.kind);
  const pct   = Math.round(d.confidence * 100);
  const label = d.kind === 'plate' && d.ocr_text ? `PLATE ${d.ocr_text}`
              : d.kind === 'plate' ? 'PLATE (unreadable)'
              : d.kind === 'face'  ? 'FACE'
              : d.label.toUpperCase();

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
      {/* confidence bar */}
      <div style={{ width: 56, height: 5, borderRadius: 3, background: colors.bg700, flexShrink: 0 }}>
        <div style={{
          height: '100%', borderRadius: 3,
          width: `${pct}%`,
          background: color,
          transition: 'width 0.3s ease',
        }} />
      </div>
      <span className="tabular-nums" style={{ fontSize: 11, color, fontWeight: 700, minWidth: 28 }}>
        {pct}%
      </span>
      <span style={{ fontSize: 11, color: colors.textHi, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {label}
      </span>
    </div>
  );
}
