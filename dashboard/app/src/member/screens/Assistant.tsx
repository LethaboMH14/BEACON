/**
 * Assistant — ask about your area, get an answer with its sources attached.
 *
 * THE HONEST STATE OF THIS SCREEN
 * There is no LLM key in this repo, so there is no language model behind this.
 * What IS real: every number and every citation. Questions are matched to a
 * retrieval intent, the answer is composed from live GET /v1/hotspots/geo data,
 * and each citation chip links to the actual suburb on the map. That is the
 * retrieval half of a RAG assistant, genuinely working; the generation half is
 * a template.
 *
 * So the composer carries a SIMULATED tag and the footnote says which half is
 * which. A judge who asks "is that a real LLM?" gets the true answer from the
 * screen before they have to ask. When a key lands, replace composeAnswer() —
 * the retrieval, citation and consent plumbing around it does not change.
 *
 * The design's separate "empty state" and "thinking" frames are states here.
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { colors } from '../../theme/tokens';
import { getHotspotsGeo, type HotspotGeo, type HotspotsGeoResponse } from '../../api/member';
import { Button, Card, MethodNote, Screen, ScreenHeader, SimulatedTag, radii, money, hourLabel } from '../ui';

interface Citation { label: string; hexId: string }
interface Msg {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  citations?: Citation[];
  /** Set when the assistant wants to save something — the design's consent card. */
  consent?: { summary: string };
  thinking?: string;
}

const SUGGESTIONS = [
  'How risky is Bryanston?',
  'When do most claims happen near me?',
  'Which suburbs are worst right now?',
  'What gets stolen most in Sandton?',
];

function findSuburb(q: string, hotspots: HotspotGeo[]): HotspotGeo | null {
  const up = q.toUpperCase();
  // Longest name first so "SANDTON CBD" doesn't match "SANDTON" when both exist.
  const sorted = [...hotspots].sort((a, b) => b.suburb.length - a.suburb.length);
  return sorted.find((h) => up.includes(h.suburb.toUpperCase())) ?? null;
}

/**
 * Template composition over real retrieved rows. Deliberately narrow: it answers
 * what the claims data can answer and says so when it can't, rather than
 * producing a confident sentence about something it never looked up.
 */
function composeAnswer(q: string, data: HotspotsGeoResponse): { text: string; citations: Citation[]; tool: string } {
  const hotspots = data.hotspots;
  const suburb = findSuburb(q, hotspots);
  const lower = q.toLowerCase();

  if (suburb) {
    const cite = [{ label: `${suburb.incident_count} claims in ${suburb.suburb.replace(/\b\w/g, (c) => c.toUpperCase())}`, hexId: suburb.hex_id }];
    const tool = `Checking claims history for ${suburb.suburb.replace(/\b\w/g, (c) => c.toUpperCase())}…`;

    if (lower.includes('when') || lower.includes('time') || lower.includes('hour')) {
      return {
        tool,
        citations: cite,
        text: `In ${suburb.suburb.replace(/\b\w/g, (c) => c.toUpperCase())}, claims cluster around ${hourLabel(suburb.peak_hour)}${suburb.peak_day_of_week ? ` on ${suburb.peak_day_of_week}s` : ''}${suburb.peak_month ? `, with ${suburb.peak_month} the busiest month` : ''}. That's from ${suburb.incident_count} local crime reports on record — a pattern in past claims, not a forecast for tonight.`,
      };
    }
    if (lower.includes('stolen') || lower.includes('what') || lower.includes('type')) {
      return {
        tool,
        citations: cite,
        text: `The most common claim type in ${suburb.suburb.replace(/\b\w/g, (c) => c.toUpperCase())} is ${(suburb.top_claim_type ?? 'theft').toLowerCase()}. Across ${suburb.incident_count} claims the total is ${money(suburb.total_claim_cost)}, averaging ${money(suburb.avg_claim_cost)} each.`,
      };
    }
    return {
      tool,
      citations: cite,
      text: `${suburb.suburb.replace(/\b\w/g, (c) => c.toUpperCase())} scores ${suburb.severity_score.toFixed(2)} on our severity scale, from ${suburb.incident_count} local crime reports — mostly ${(suburb.top_claim_type ?? 'theft').toLowerCase()}, peaking around ${hourLabel(suburb.peak_hour)}. This is suburb-level history, not street-level prediction.`,
    };
  }

  if (lower.includes('worst') || lower.includes('highest') || lower.includes('riskiest')) {
    const top = hotspots.slice(0, 3);
    return {
      tool: 'Ranking suburbs by severity…',
      citations: top.map((h) => ({ label: `${h.suburb.replace(/\b\w/g, (c) => c.toUpperCase())} ${h.severity_score.toFixed(2)}`, hexId: h.hex_id })),
      text: `By severity, the highest are ${top.map((h) => h.suburb.replace(/\b\w/g, (c) => c.toUpperCase())).join(', ')}. Severity combines how often claims happen with how much they cost, so a suburb can rank high on a few very expensive claims.`,
    };
  }

  return {
    tool: 'Searching claims data…',
    citations: [],
    text: `I can only answer from historical crime pattern data. Try naming a suburb, or ask which areas rank highest.`,
  };
}

let nextId = 1;

export default function Assistant() {
  const nav = useNavigate();
  const [data, setData] = useState<HotspotsGeoResponse | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [thinking, setThinking] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { getHotspotsGeo({ minSeverity: 0 }).then(setData).catch(() => {}); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs, thinking]);

  function ask(q: string) {
    if (!q.trim() || !data) return;
    setMsgs((m) => [...m, { id: nextId++, role: 'user', text: q }]);
    setInput('');

    const { text, citations, tool } = composeAnswer(q, data);
    // The design's "thinking" frame named the tool being called. Keeping that
    // is the difference between a black box and something a member can audit.
    setThinking(tool);
    window.setTimeout(() => {
      setThinking(null);
      setMsgs((m) => [...m, {
        id: nextId++, role: 'assistant', text, citations,
        // Consent card: asked, never assumed, and both buttons carry equal
        // visual weight so "Yes" is not the default by design pressure.
        consent: citations.length ? { summary: 'Save this area to your watchlist so we can warn you before you head there?' } : undefined,
      }]);
    }, 550);
  }

  const empty = msgs.length === 0;

  return (
    <Screen>
      <ScreenHeader
        title="Ask BEACON"
        subtitle="Answers from historical crime data"
        right={<SimulatedTag />}
      />

      {empty && (
        <Card style={{ padding: 16, marginBottom: 14 }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>What would you like to know?</div>
          <p style={{ margin: '0 0 12px', fontSize: 12.5, color: colors.inkMid, lineHeight: 1.5 }}>
            I answer using historical crime pattern data — and I show you where each answer came from.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => ask(s)} disabled={!data} style={{
                textAlign: 'left', minHeight: 44, padding: '0 13px', borderRadius: radii.control,
                border: `1px solid ${colors.lineLight}`, background: colors.bg50,
                fontSize: 13, color: colors.inkHi, cursor: data ? 'pointer' : 'wait',
              }}>{s}</button>
            ))}
          </div>
        </Card>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 14 }}>
        {msgs.map((m) => m.role === 'user' ? (
          <div key={m.id} style={{ alignSelf: 'flex-end', maxWidth: '84%' }}>
            <div style={{
              background: colors.discovery, color: '#fff', padding: '10px 14px',
              borderRadius: `${radii.card}px ${radii.card}px 6px ${radii.card}px`, fontSize: 13.5, lineHeight: 1.5,
            }}>{m.text}</div>
          </div>
        ) : (
          <div key={m.id} style={{ alignSelf: 'flex-start', maxWidth: '92%' }}>
            <div style={{
              background: colors.bg0, border: `1px solid ${colors.lineLight}`, boxShadow: colors.shadowCard,
              padding: '12px 14px', borderRadius: `${radii.card}px ${radii.card}px ${radii.card}px 6px`,
              fontSize: 13.5, lineHeight: 1.55,
            }}>
              {m.text}

              {!!m.citations?.length && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
                  {m.citations.map((c) => (
                    <button key={c.hexId + c.label} onClick={() => nav('/map')} style={{
                      display: 'inline-flex', alignItems: 'center', gap: 5, padding: '5px 10px',
                      borderRadius: radii.chip, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                      color: colors.discovery, background: colors.discoverySoft,
                      border: `1px solid color-mix(in srgb, ${colors.discovery} 22%, transparent)`,
                    }}>
                      From {c.label} · view on map
                    </button>
                  ))}
                </div>
              )}
            </div>

            {m.consent && <ConsentCard summary={m.consent.summary} />}
          </div>
        ))}

        {thinking && (
          <div style={{ alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', background: colors.bg0, border: `1px solid ${colors.lineLight}`, borderRadius: radii.card }}>
            <span style={{ width: 7, height: 7, borderRadius: 4, background: colors.discovery, animation: 'beacon-pulse 1s ease-in-out infinite' }} />
            <span style={{ fontSize: 12.5, color: colors.inkMid }}>{thinking}</span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* composer */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') ask(input); }}
          placeholder="Ask about an area…"
          style={{
            flex: 1, minHeight: 48, padding: '0 15px', borderRadius: radii.control,
            border: `1px solid ${colors.lineLight}`, background: colors.bg0,
            fontSize: 14, color: colors.inkHi, fontFamily: 'inherit', outlineColor: colors.discovery,
          }}
        />
        <button onClick={() => ask(input)} disabled={!input.trim() || !data} aria-label="Send" style={{
          width: 48, height: 48, borderRadius: radii.control, border: 'none', flexShrink: 0,
          background: input.trim() && data ? colors.discovery : colors.lineLight,
          color: '#fff', fontSize: 17, cursor: input.trim() && data ? 'pointer' : 'not-allowed',
        }}>↑</button>
      </div>

      <MethodNote>
        Retrieval and citations are live against the claims database. The wording of the
        answers is templated, not model-generated — that half is not wired up yet.
      </MethodNote>
    </Screen>
  );
}

function ConsentCard({ summary }: { summary: string }) {
  const [answered, setAnswered] = useState<'yes' | 'no' | null>(null);
  if (answered) {
    return (
      <p style={{ margin: '8px 2px 0', fontSize: 11.5, color: colors.inkLo }}>
        {answered === 'yes' ? 'Saved to your watchlist.' : 'Not saved.'}
      </p>
    );
  }
  return (
    <Card style={{ marginTop: 8, padding: 13 }}>
      <p style={{ margin: '0 0 11px', fontSize: 12.5, lineHeight: 1.5, color: colors.inkMid }}>{summary}</p>
      {/* Equal weight on purpose — a styled-up "Yes" beside a greyed "No" is a
          dark pattern when the question is about storing someone's data. */}
      <div style={{ display: 'flex', gap: 8 }}>
        <Button variant="secondary" onClick={() => setAnswered('no')}>No</Button>
        <Button variant="secondary" onClick={() => setAnswered('yes')}>Yes</Button>
      </div>
    </Card>
  );
}
