import { create } from "zustand";
import { immer } from "zustand/middleware/immer";

type FSMState =
  | "IDLE"
  | "PERCEPTION_ROUTING"
  | "RAG_RETRIEVAL"
  | "INTERNAL_ITERATION"
  | "OPERATOR_READY"
  | "PENDING_HUMAN_CONFLICT"
  | "BROKEN_PACT"
  | "EXECUTION"
  | "MEMORY_CONSOLIDATION"
  | "PROMPT_BLOATING"
  | "ERROR";

type ConfidenceState = "convergent" | "partial" | "conflict" | null;

interface SystemState {
  fsmState: FSMState;
  streamBuffer: string;
  activePactId: string | null;
  activePactSummary: string | null;
  confidenceState: ConfidenceState;
  sessionId: string | null;
  isConnected: boolean;
  setFSMState: (state: FSMState) => void;
  appendToken: (token: string) => void;
  clearStream: () => void;
  setPact: (pactId: string, summary: string) => void;
  clearPact: () => void;
  setConfidence: (state: ConfidenceState) => void;
  setConnected: (connected: boolean) => void;
}

export const useSystemStore = create<SystemState>()(
  immer((set) => ({
    fsmState: "IDLE",
    streamBuffer: "",
    activePactId: null,
    activePactSummary: null,
    confidenceState: null,
    sessionId: null,
    isConnected: false,

    setFSMState: (state) =>
      set((draft) => {
        draft.fsmState = state;
      }),
    appendToken: (token) =>
      set((draft) => {
        draft.streamBuffer += token;
      }),
    clearStream: () =>
      set((draft) => {
        draft.streamBuffer = "";
      }),
    setPact: (id, summary) =>
      set((draft) => {
        draft.activePactId = id;
        draft.activePactSummary = summary;
      }),
    clearPact: () =>
      set((draft) => {
        draft.activePactId = null;
        draft.activePactSummary = null;
      }),
    setConfidence: (state) =>
      set((draft) => {
        draft.confidenceState = state;
      }),
    setConnected: (connected) =>
      set((draft) => {
        draft.isConnected = connected;
      })
  }))
);
