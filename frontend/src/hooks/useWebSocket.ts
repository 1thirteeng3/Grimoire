import { useCallback, useEffect, useRef } from "react";
import type { MutableRefObject } from "react";

import { useSystemStore } from "../store/system";
import type { components as WsComponents } from "../types/ws_events";

type ServerEvent = WsComponents["schemas"]["ServerEvent"];

const WS_URL = "ws://127.0.0.1:8000/ws";
const PING_INTERVAL_MS = 15_000;
const PONG_TIMEOUT_MS = 5_000;
const MAX_BACKOFF_MS = 30_000;

export function useWebSocket(sessionId: string) {
  const ws = useRef<WebSocket | null>(null);
  const backoff = useRef(1000);
  const pongTimer = useRef<ReturnType<typeof setTimeout>>();
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const shouldReconnect = useRef(true);

  const connect = useCallback(() => {
    if (!shouldReconnect.current) {
      return;
    }
    ws.current = new WebSocket(`${WS_URL}/${sessionId}`);
    ws.current.onopen = () => {
      useSystemStore.getState().setConnected(true);
      backoff.current = 1000;
    };
    ws.current.onclose = () => {
      useSystemStore.getState().setConnected(false);
      if (!shouldReconnect.current) {
        return;
      }
      reconnectTimer.current = setTimeout(connect, backoff.current);
      backoff.current = Math.min(backoff.current * 2, MAX_BACKOFF_MS);
    };
    ws.current.onmessage = (evt) => {
      const event: ServerEvent = JSON.parse(evt.data);
      handleEvent(event, pongTimer);
    };
  }, [sessionId]);

  useEffect(() => {
    shouldReconnect.current = true;
    connect();
    const pingInterval = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({ type: "PING" }));
        pongTimer.current = setTimeout(() => {
          ws.current?.close();
        }, PONG_TIMEOUT_MS);
      }
    }, PING_INTERVAL_MS);

    return () => {
      shouldReconnect.current = false;
      clearInterval(pingInterval);
      clearTimeout(reconnectTimer.current);
      clearTimeout(pongTimer.current);
      ws.current?.close();
    };
  }, [connect]);

  return {
    ws: ws.current,
    sendMessage: (msg: object) => ws.current?.send(JSON.stringify(msg))
  };
}

function handleEvent(
  event: ServerEvent,
  pongTimer: MutableRefObject<ReturnType<typeof setTimeout> | undefined>
) {
  const store = useSystemStore.getState();
  switch (event.type) {
    case "STATE_RAG_RETRIEVAL":
      store.setFSMState("RAG_RETRIEVAL");
      break;
    case "STREAM_TOKEN":
      store.appendToken(event.payload.delta);
      break;
    case "CONFIDENCE_UPDATE":
      store.setConfidence(event.payload.state);
      break;
    case "PACT_REQUEST":
      store.setFSMState("PENDING_HUMAN_CONFLICT");
      store.setPact(event.payload.pact_id, event.payload.human_summary);
      break;
    case "EXECUTION_SUCCESS":
      store.setFSMState("MEMORY_CONSOLIDATION");
      break;
    case "PROMPT_BLOATING":
      store.setFSMState("PROMPT_BLOATING");
      break;
    case "PONG":
      clearTimeout(pongTimer.current);
      break;
    default: {
      const _exhaustive: never = event;
      return _exhaustive;
    }
  }
}
