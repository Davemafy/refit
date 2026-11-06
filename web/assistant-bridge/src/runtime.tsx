"use client";

import type { ReactNode } from "react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { refitAdapter } from "./adapter";

/**
 * Drop-in wrapper: keep the final UI completely independent of this preview.
 * Handles message/threads/cancellation through assistant-ui's LocalRuntime.
 * Requests are same-origin and read-only; migration execution stays on Python.
 */
export function RefitRuntimeProvider({ children }: { children: ReactNode }) {
  const runtime = useLocalRuntime(refitAdapter);
  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}
