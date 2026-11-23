import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../services/api.js";
import { frameIndexAt, isKeyEvent } from "../services/timeline.js";

const TICK_MS = 100; // how often the playback cursor moves

// State of the 4D timeline: live or replay, the recorded frames, the playback cursor.
export function useTimeline() {
  const [replay, setReplay] = useState(false);
  const [data, setData] = useState(null); // { frames, events, start_ms, end_ms }
  const [cursor, setCursor] = useState(0); // the moment being shown (epoch ms)
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(5);
  const [minutes, setMinutes] = useState(30);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async (mins, keepCursor = false) => {
    setLoading(true);
    try {
      const d = await api.timelineFrames(mins || undefined);
      const events = d.events.map((e) => ({ ...e, t: Date.parse(e.timestamp) }));
      setData({ ...d, events });
      setCursor((c) => (keepCursor && c >= (d.start_ms ?? 0) && c <= (d.end_ms ?? 0) ? c : d.start_ms ?? 0));
      setError(d.count === 0 ? "Nothing recorded yet. Let the simulation run for a few seconds." : null);
      return d;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const enterReplay = useCallback(async () => {
    const d = await load(minutes);
    if (d && d.count > 0) {
      setReplay(true);
      setPlaying(false);
    }
  }, [load, minutes]);

  const exitReplay = useCallback(() => {
    setReplay(false);
    setPlaying(false);
  }, []);

  const changeRange = useCallback(
    (mins) => {
      setMinutes(mins);
      if (replay) load(mins);
    },
    [replay, load]
  );

  // Playback: move the cursor forward at the chosen speed; stop at the end.
  useEffect(() => {
    if (!replay || !playing || !data) return undefined;
    const timer = setInterval(() => {
      setCursor((c) => {
        const next = c + TICK_MS * speed;
        if (next >= data.end_ms) {
          setPlaying(false);
          return data.end_ms;
        }
        return next;
      });
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [replay, playing, speed, data]);

  const frame = useMemo(() => {
    if (!replay || !data?.frames.length) return null;
    return data.frames[frameIndexAt(data.frames, cursor)];
  }, [replay, data, cursor]);

  const keyEvents = useMemo(() => (data?.events ?? []).filter(isKeyEvent), [data]);

  const jump = useCallback(
    (direction) => {
      if (!keyEvents.length) return;
      // events are stored with 1 s precision, so look 1.5 s beyond the cursor
      const target =
        direction > 0
          ? keyEvents.find((e) => e.t > cursor + 1500)
          : [...keyEvents].reverse().find((e) => e.t < cursor - 1500);
      if (target) setCursor(Math.min(Math.max(target.t + 999, data.start_ms), data.end_ms));
    },
    [keyEvents, cursor, data]
  );

  return {
    replay, data, cursor, setCursor, playing, setPlaying, speed, setSpeed, minutes, changeRange,
    loading, error, frame, keyEvents, enterReplay, exitReplay, reload: () => load(minutes, true), jump,
  };
}
