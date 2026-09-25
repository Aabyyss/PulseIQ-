import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RiskLevel } from "@/components/app/risk-pill";
import { getToken } from "@/lib/auth";
import {
  deriveLocalClinicalGuidance,
  inferBodyPainInsights,
  mergeInsights,
  type BodyPainInsight
} from "@/lib/bodyPain";
import { getConsultationSocketCandidates } from "@/lib/realtime";
import type { RealtimeConsultationEvent } from "@/lib/types";

export type TranscriptLine = {
  id: string;
  speaker: "doctor" | "patient";
  text: string;
  timestamp: string;
};

export type CardiacRegionEntry = RealtimeConsultationEvent["cardiac_regions"][number];

export const LANGUAGE_OPTIONS = [
  { label: "English", code: "en-US" },
  { label: "Urdu", code: "ur-PK" },
  { label: "Hindi", code: "hi-IN" },
  { label: "Arabic", code: "ar-SA" },
  { label: "Korean", code: "ko-KR" },
  { label: "French", code: "fr-FR" },
  { label: "Spanish", code: "es-ES" },
  { label: "German", code: "de-DE" },
  { label: "Chinese (Mandarin)", code: "zh-CN" }
];

type LineAckEvent = {
  kind: "line_ack";
  speaker: "doctor" | "patient";
  transcript: string;
  original_transcript?: string;
  symptoms?: string[];
};

const MAX_LINES = 200;

/*
 * Who-is-speaking heuristic: the patient tells or informs about symptoms in
 * the first person ("it pains in my heart", "mujhe chakkar aa rahe hain");
 * the clinician informs about the case ("the patient reports…", "on
 * examination…", "start a troponin"). Counted cues decide per line; a
 * symptom-style fragment with no cue at all reads as the patient.
 */
const PATIENT_SPEECH_CUES = [
  /\bi\b/, /\bim\b/, /\bi'm\b/, /\bive\b/, /\bi've\b/, /\bill\b/, /\bi'll\b/, /\bmy\b/, /\bme\b/, /\bmine\b/, /\bmyself\b/,
  /\bmujhe\b/, /\bmera\b/, /\bmeri\b/, /\bmeray\b/, /\bmere\b/, /\bmain(?:\s+(?:ne|ko|se))?\b/, /\bmera?\b/,
  /\bje\b/, /\bjeo\b/, /\bnae\b/, /\bnaui\b/, /\bmaneun\b/
];
const DOCTOR_SPEECH_CUES = [
  /\bpatient\b/, /\b(?:his|her|their)\s+history\b/, /\bpresents?\b/, /\bcomplain(?:s|ing)?\s+of\b/,
  /\bon\s+examination\b/, /\bauscultation\b/, /\bvitals?\b/, /\bbp\b/, /\bstethoscope\b/,
  /\bdiagnos(?:is|e)\b/, /\bimpression\b/, /\brecommend\b/, /\breferr?(?:al|ing)\b/, /\badmit\b/,
  /\bprescrib\w*/, /\bdosage\b/, /\bmg\s+daily\b/, /\borders?\b/, /\blet'?s\s+(?:start|check|order)\b/,
  /\byou\s+(?:should|need|have|can)\b/, /\bprint\b/, /\bsave\s+this\b/
];

function detectSpeaker(text: string, fallback: "doctor" | "patient"): "doctor" | "patient" {
  const lower = ` ${text.toLowerCase()} `;
  let patientScore = 0;
  let doctorScore = 0;
  PATIENT_SPEECH_CUES.forEach((cue) => {
    if (cue.test(lower)) patientScore += 1;
  });
  DOCTOR_SPEECH_CUES.forEach((cue) => {
    if (cue.test(lower)) doctorScore += 2; // clinical cues are rarer and more decisive
  });
  if (patientScore > 0 && doctorScore === 0) return "patient";
  if (doctorScore > 0 && patientScore === 0) return "doctor";
  if (patientScore > 0 && doctorScore > 0) return "patient"; // symptom-telling wins the tie
  return fallback;
}

/**
 * One capture engine for the whole consultation flow, replacing the two
 * near-duplicate implementations in the old live-copilot and workflow pages.
 *
 * Local-first: every line instantly appends to the transcript, the body map
 * accumulates across the whole encounter (a later line never wipes earlier
 * regions), and regex symptoms from the server's line ack appear without
 * waiting for the LLM. The full copilot plan arrives separately as an
 * analysis event once the local model finishes.
 */
export function useConsultationCapture() {
  const [speaker, setSpeakerState] = useState<"doctor" | "patient">("patient");
  const [autoSpeaker, setAutoSpeakerState] = useState(true);
  const [language, setLanguageState] = useState("en-US");
  const [isListening, setIsListening] = useState(false);
  const [micState, setMicState] = useState<"idle" | "granted" | "denied">("idle");
  const [connected, setConnected] = useState(false);
  const [awaitingCopilot, setAwaitingCopilot] = useState(false);
  const [error, setError] = useState("");
  const [lastHeard, setLastHeard] = useState("");
  const [interimText, setInterimText] = useState("");
  const [listeningHint, setListeningHint] = useState("");
  const [draft, setDraft] = useState("");
  const [reportText, setReportText] = useState("");

  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [symptoms, setSymptoms] = useState<string[]>([]);
  const [bodyInsights, setBodyInsights] = useState<BodyPainInsight[]>([]);
  const [riskLevel, setRiskLevel] = useState<RiskLevel>("Low");
  const [doctorQuestions, setDoctorQuestions] = useState<string[]>([]);
  const [recommendedTests, setRecommendedTests] = useState<string[]>([]);
  const [diagnosticImpression, setDiagnosticImpression] = useState<string[]>([]);
  const [nextSteps, setNextSteps] = useState<string[]>([]);
  const [patientRecommendations, setPatientRecommendations] = useState<string[]>([]);
  const [safetyNote, setSafetyNote] = useState("");
  const [cardiacRegions, setCardiacRegions] = useState<CardiacRegionEntry[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const keepListeningRef = useRef(false);
  const restartTimerRef = useRef<number | null>(null);
  const linesRef = useRef<TranscriptLine[]>([]);
  const speakerRef = useRef(speaker);
  const autoSpeakerRef = useRef(autoSpeaker);
  const languageRef = useRef(language);
  const reportTextRef = useRef(reportText);
  const analysisSeqRef = useRef(0);

  speakerRef.current = speaker;
  autoSpeakerRef.current = autoSpeaker;
  languageRef.current = language;
  reportTextRef.current = reportText;

  const speechSupported = useMemo(
    () => Boolean(window.SpeechRecognition || window.webkitSpeechRecognition),
    []
  );

  // ------------------------------------------------------------------
  // Insight accumulation — over the FULL transcript, never just a line
  // ------------------------------------------------------------------
  const recomputeBodyInsights = useCallback(() => {
    const allText = linesRef.current.map((line) => line.text).join(" ");
    const incoming = inferBodyPainInsights(allText, reportTextRef.current);
    setBodyInsights((prev) => mergeInsights(prev, incoming, allText));
  }, []);

  const addSymptoms = useCallback((found: string[]) => {
    if (!found.length) return;
    setSymptoms((prev) => {
      const next = new Set(prev.map((s) => s.toLowerCase()));
      let changed = false;
      found.forEach((s) => {
        const key = s.toLowerCase();
        if (!next.has(key)) {
          next.add(key);
          changed = true;
        }
      });
      return changed ? Array.from(next) : prev;
    });
  }, []);

  // ------------------------------------------------------------------
  // Realtime socket — candidate fallback like the old workflow page
  // ------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    let activeSocket: WebSocket | null = null;

    const handleAck = (payload: LineAckEvent) => {
      addSymptoms(payload.symptoms ?? []);
      recomputeBodyInsights();
    };

    const handleAnalysis = (payload: RealtimeConsultationEvent) => {
      const seq = ++analysisSeqRef.current;
      setAwaitingCopilot(false);
      addSymptoms(payload.symptoms ?? []);
      recomputeBodyInsights();

      // Normalise the displayed line to the English translation.
      const original = payload.original_transcript?.trim();
      const english = payload.transcript?.trim();
      if (original && english && original.toLowerCase() !== english.toLowerCase()) {
        setLines((prev) => {
          const next = [...prev];
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].text.trim().toLowerCase() === original.toLowerCase()) {
              next[i] = { ...next[i], text: english };
              linesRef.current = next;
              break;
            }
          }
          return next;
        });
      }

      setRiskLevel(payload.diagnosis?.risk_level ?? "Low");
      setDoctorQuestions(payload.ai_copilot?.doctor_questions ?? payload.doctor_next_questions ?? []);
      setRecommendedTests(payload.ai_copilot?.recommended_tests ?? []);
      setDiagnosticImpression(payload.ai_copilot?.diagnostic_impression ?? []);
      setNextSteps(payload.ai_copilot?.next_steps ?? payload.patient_recommendations ?? []);
      setPatientRecommendations(payload.patient_recommendations ?? []);
      setSafetyNote(payload.ai_copilot?.safety_note ?? "");
      setCardiacRegions(payload.cardiac_regions ?? []);
      return seq;
    };

    const onMessage = (event: MessageEvent) => {
      let payload: (LineAckEvent | RealtimeConsultationEvent) & { kind?: string };
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (!payload.kind && "error" in payload && payload.error) {
        setError(String(payload.error));
        setAwaitingCopilot(false);
        return;
      }
      if (payload.kind === "line_ack") {
        handleAck(payload as LineAckEvent);
      } else {
        handleAnalysis(payload as RealtimeConsultationEvent);
      }
    };

    const tryConnect = (candidates: string[]) => {
      if (cancelled || candidates.length === 0) {
        setConnected(false);
        setError(
          "Realtime engine offline — on-device triage guidance is active. Start the PulseIQ backend on port 8000 for the full copilot."
        );
        return;
      }
      const token = getToken();
      const ws = new WebSocket(candidates[0] + (token ? `?token=${encodeURIComponent(token)}` : ""));
      let opened = false;

      ws.onopen = () => {
        if (cancelled) {
          ws.close();
          return;
        }
        opened = true;
        activeSocket = ws;
        wsRef.current = ws;
        setConnected(true);
        setError(""); // a later reconnect must clear an earlier failure banner
        ws.onmessage = onMessage;
      };
      ws.onerror = () => {
        if (opened || cancelled) return;
        ws.close();
        tryConnect(candidates.slice(1));
      };
      ws.onclose = () => {
        if (cancelled || !opened) return;
        setConnected(false);
      };
    };

    tryConnect(getConsultationSocketCandidates());

    return () => {
      cancelled = true;
      activeSocket?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ------------------------------------------------------------------
  // Sending lines
  // ------------------------------------------------------------------
  const pushLine = useCallback(
    (text: string, lineSpeaker: "doctor" | "patient") => {
      const entry: TranscriptLine = {
        id: crypto.randomUUID(),
        speaker: lineSpeaker,
        text,
        timestamp: new Date().toLocaleTimeString()
      };
      const next = [...linesRef.current, entry].slice(-MAX_LINES);
      linesRef.current = next;
      setLines(next);
      recomputeBodyInsights();
    },
    [recomputeBodyInsights]
  );

  const sendLine = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setInterimText("");
      setLastHeard(trimmed);
      setError("");

      // Attribute the line: auto-detected from the wording, or the manual
      // toggle when auto-detection is switched off.
      const lineSpeaker = autoSpeakerRef.current
        ? detectSpeaker(trimmed, speakerRef.current)
        : speakerRef.current;
      setSpeakerState(lineSpeaker);
      pushLine(trimmed, lineSpeaker);

      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        const localPlan = deriveLocalClinicalGuidance(
          inferBodyPainInsights(linesRef.current.map((l) => l.text).join(" "), reportTextRef.current)
        );
        setDoctorQuestions(localPlan.doctorQuestions);
        setRecommendedTests(localPlan.recommendedTests);
        setNextSteps(localPlan.nextSteps);
        setDiagnosticImpression(["Local mode: backend disconnected — showing on-device triage hints only."]);
        setError("Realtime engine offline — on-device triage guidance is active.");
        return;
      }
      setAwaitingCopilot(true);
      wsRef.current.send(
        JSON.stringify({
          speaker: lineSpeaker,
          text: trimmed,
          report_text: reportTextRef.current,
          language_code: languageRef.current
        })
      );
    },
    [pushLine]
  );

  const submitDraft = useCallback(() => {
    const value = draft.trim();
    if (!value) return;
    setDraft("");
    sendLine(value);
  }, [draft, sendLine]);

  const clearTranscript = useCallback(() => {
    linesRef.current = [];
    setLines([]);
    setSymptoms([]);
    setBodyInsights([]);
    setInterimText("");
    setAwaitingCopilot(false);
    setRiskLevel("Low");
    setDoctorQuestions([]);
    setRecommendedTests([]);
    setDiagnosticImpression([]);
    setNextSteps([]);
    setPatientRecommendations([]);
    setSafetyNote("");
    setCardiacRegions([]);
  }, []);

  // ------------------------------------------------------------------
  // Speech capture — permission preflight + interim results
  // ------------------------------------------------------------------
  const preflightMic = useCallback(async (): Promise<boolean> => {
    if (!navigator.mediaDevices?.getUserMedia) return true; // let the recognizer try
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      setMicState("granted");
      return true;
    } catch {
      setMicState("denied");
      setError(
        "Microphone blocked. Click the lock (or site settings) icon in the address bar, allow Microphone, then start listening again."
      );
      return false;
    }
  }, []);

  const startListening = useCallback(async () => {
    if (!speechSupported) {
      setError("Speech recognition is not supported in this browser. Use Chrome or Edge.");
      return;
    }
    if (!window.isSecureContext) {
      setError("Microphone access requires localhost or an HTTPS secure context.");
      return;
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;

    const micOk = await preflightMic();
    if (!micOk) return;

    setError("");
    const recognition = new SR();
    recognition.continuous = true;
    recognition.interimResults = true; // show words as they are spoken
    recognition.lang = languageRef.current;

    recognition.onresult = (event) => {
      const evt = event as SpeechRecognitionEvent & { resultIndex: number };
      let interim = "";
      for (let i = evt.resultIndex; i < evt.results.length; i++) {
        const result = evt.results[i];
        const text = result[0].transcript;
        if (result.isFinal) {
          const trimmed = text.trim();
          if (!trimmed) continue;
          // ASR noise produces junk finals ("uh", "a", "mmm") that would
          // otherwise become transcript lines and dilute the analysis.
          const wordCount = trimmed.split(/\s+/).length;
          if (wordCount < 2 && !/[\u0600-\u06ff\uac00-\ud7af]/.test(trimmed) && trimmed.length < 4) {
            setLastHeard(trimmed);
            setListeningHint(
              /[\u0600-\u06ff]/.test(trimmed) || languageRef.current === "ur-PK"
                ? "واضح سنائی دیجیے — یہ سطر شامل نہیں ہوئی۔"
                : "That wasn't clear enough to include — try speaking a little closer to the mic."
            );
            continue;
          }
          setListeningHint("");
          sendLine(trimmed);
        } else {
          interim += text;
          setListeningHint("");
        }
      }
      setInterimText(interim.trim());
    };

    recognition.onerror = (event) => {
      const errorName = (event as Event & { error?: string }).error;
      if (errorName === "not-allowed" || errorName === "service-not-allowed") {
        setError("Microphone permission denied. Allow mic access in your browser site settings.");
        keepListeningRef.current = false;
        setIsListening(false);
        return;
      }
      if (errorName === "no-speech" || errorName === "aborted") {
        // Normal pauses: keep the session alive, surface a gentle hint only.
        setInterimText("");
        return;
      }
      if (errorName === "network") {
        setError("Speech service unreachable — check internet connectivity, then start listening again.");
        keepListeningRef.current = false;
        setIsListening(false);
        return;
      }
      if (!keepListeningRef.current) {
        setError("Microphone error. Check permissions and the selected input device.");
        setIsListening(false);
      }
    };

    recognition.onend = () => {
      setInterimText("");
      if (keepListeningRef.current) {
        if (restartTimerRef.current) window.clearTimeout(restartTimerRef.current);
        restartTimerRef.current = window.setTimeout(() => {
          try {
            recognition.start();
          } catch {
            setIsListening(false);
          }
        }, 250);
        return;
      }
      setIsListening(false);
    };

    try {
      recognition.start();
    } catch {
      setError("Could not start the microphone. Close other apps using it and try again.");
      return;
    }
    recognitionRef.current = recognition;
    keepListeningRef.current = true;
    setIsListening(true);
  }, [preflightMic, sendLine, speechSupported]);

  const stopListening = useCallback(() => {
    if (restartTimerRef.current) {
      window.clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    keepListeningRef.current = false;
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setInterimText("");
    setListeningHint("");
    setIsListening(false);
  }, []);

  const toggleListening = useCallback(() => {
    if (keepListeningRef.current) stopListening();
    else void startListening();
  }, [startListening, stopListening]);

  const setSpeaker = useCallback((role: "doctor" | "patient") => {
    setSpeakerState(role);
    setAutoSpeakerState(false); // a manual pick takes over attribution
  }, []);

  const setAutoSpeaker = useCallback((enabled: boolean) => {
    setAutoSpeakerState(enabled);
    if (enabled) setSpeakerState("patient"); // re-detect from the next line
  }, []);

  const changeLanguage = useCallback(
    (code: string) => {
      languageRef.current = code;
      setLanguageState(code);
      if (keepListeningRef.current) {
        // The recognizer reads lang at start(); restart with the new locale.
        keepListeningRef.current = false;
        recognitionRef.current?.stop();
        recognitionRef.current = null;
        window.setTimeout(() => {
          void startListening();
        }, 350);
      }
    },
    [startListening]
  );

  useEffect(
    () => () => {
      if (restartTimerRef.current) window.clearTimeout(restartTimerRef.current);
      keepListeningRef.current = false;
      recognitionRef.current?.stop();
    },
    []
  );

  return {
    // session controls
    speaker,
    setSpeaker,
    autoSpeaker,
    setAutoSpeaker,
    language,
    changeLanguage,
    isListening,
    toggleListening,
    startListening,
    stopListening,
    micState,
    speechSupported,
    // capture state
    lines,
    interimText,
    listeningHint,
    lastHeard,
    draft,
    setDraft,
    submitDraft,
    sendLine,
    clearTranscript,
    reportText,
    setReportText,
    // engine state
    connected,
    awaitingCopilot,
    error,
    // analysis
    symptoms,
    riskLevel,
    bodyInsights,
    doctorQuestions,
    recommendedTests,
    diagnosticImpression,
    nextSteps,
    patientRecommendations,
    safetyNote,
    cardiacRegions
  };
}
