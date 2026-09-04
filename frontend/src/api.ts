// SPDX-License-Identifier: GPL-3.0-or-later
// Thin REST client for the Flask back-end. Everything funnels through here
// so we have a single place to add auth, retries, or error handling.

import type {
  ApiOk,
  InitPayload,
  SelectQuestionResponse,
  ServerState,
  SubmitAnswerPayload,
} from "@/types";

const BASE = "/api/v1";

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
}

async function request<T = unknown>(
  path: string,
  { method = "GET", body }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const opts: RequestInit = { method, headers };
  if (body instanceof FormData) {
    // Let the browser set Content-Type (with the multipart boundary).
    opts.body = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}${path}`, opts);
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    // Non-JSON body (e.g. HTML error page from the dev proxy or a crashed
    // backend). Surface the HTTP status + a snippet so it's actually
    // debuggable instead of a bare SyntaxError from JSON.parse.
    throw new Error(
      `${method} ${path} → ${res.status} ${res.statusText}: ${text.slice(0, 200)}`,
    );
  }
  if (!res.ok) {
    const msg = (data as { error?: string } | null)?.error ?? res.statusText;
    throw new Error(`${method} ${path} → ${res.status}: ${msg}`);
  }
  return data as T;
}

export const api = {
  state: () => request<ServerState>("/state"),
  roundfiles: () => request<string[]>("/roundfiles"),
  importRoundfile: (name: string, file: File) => {
    const form = new FormData();
    form.append("name", name);
    form.append("file", file);
    return request<ApiOk & { roundfiles?: string[] }>("/roundfiles/import", {
      method: "POST",
      body: form,
    });
  },

  init: (payload: InitPayload) =>
    request<ApiOk>("/init", { method: "POST", body: payload }),
  nextRound: (name: string) =>
    request<ApiOk>("/init", {
      method: "POST",
      body: { action: "next_round", name },
    }),
  updateTeams: (names: Record<string, string>) =>
    request<ApiOk>("/teams", { method: "POST", body: names }),

  selectQuestion: (id: string) =>
    request<SelectQuestionResponse>("/question/select", {
      method: "POST",
      body: { id },
    }),
  deselectQuestion: () =>
    request<ApiOk>("/question/deselect", { method: "POST" }),
  submitAnswer: (payload: SubmitAnswerPayload) =>
    request<ApiOk>("/answer", { method: "POST", body: payload }),

  selectTeam: (tid: string) =>
    request<ApiOk>("/team/select", { method: "POST", body: { tid } }),
  roulette: () => request<ApiOk>("/team/roulette", { method: "POST" }),

  setWager: (amount: number) =>
    request<ApiOk>("/dailydouble/wager", {
      method: "POST",
      body: { amount },
    }),
  revealDailyDouble: () =>
    request<ApiOk>("/dailydouble/reveal", { method: "POST" }),
  revealAnswer: () =>
    request<ApiOk>("/question/reveal-answer", { method: "POST" }),

  showMessage: (id: string, text: string) =>
    request<ApiOk>("/message/show", {
      method: "POST",
      body: { id, text },
    }),
  hideMessage: () => request<ApiOk>("/message/hide", { method: "POST" }),

  finish: () => request<ApiOk>("/finish", { method: "POST" }),

  finalStart: () => request<ApiOk>("/final/start", { method: "POST" }),
  finalWager: (tid: string, amount: number) =>
    request<ApiOk>("/final/wager", { method: "POST", body: { tid, amount } }),
  finalReveal: () => request<ApiOk>("/final/reveal", { method: "POST" }),
  finalCancel: () => request<ApiOk>("/final/cancel", { method: "POST" }),
  finalAnswer: (tid: string, correct: boolean) =>
    request<ApiOk>("/final/answer", {
      method: "POST",
      body: { tid, correct },
    }),

  setSliderState: (id: string, value: string | number) =>
    request<ApiOk>("/slider", { method: "POST", body: { id, value } }),
};
