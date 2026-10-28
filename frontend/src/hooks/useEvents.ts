import { useEffect, useRef } from "react";
import type { ServerEvent } from "../api/types";

const MIN_DELAY_MS = 1000;
const MAX_DELAY_MS = 10000;

function socketUrl(): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/ws`;
}

/** Subscribe to the backend event stream; reconnects with a 1 s, doubling, max 10 s delay. */
export function useEvents(onEvent: (e: ServerEvent) => void): void {
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = MIN_DELAY_MS;
    let stopped = false;

    const connect = () => {
      socket = new WebSocket(socketUrl());
      socket.onopen = () => {
        delay = MIN_DELAY_MS;
      };
      socket.onmessage = (msg) => {
        try {
          handler.current(JSON.parse(msg.data as string) as ServerEvent);
        } catch {
          // ignore malformed frames
        }
      };
      socket.onclose = () => {
        if (stopped) return;
        timer = setTimeout(connect, delay);
        delay = Math.min(delay * 2, MAX_DELAY_MS);
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      socket?.close();
    };
  }, []);
}
