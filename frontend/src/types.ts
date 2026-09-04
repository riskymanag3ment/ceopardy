// SPDX-License-Identifier: GPL-3.0-or-later
// Type shapes shared across the front-end. Mirror the JSON the Python back-end
// emits (see ceopardy/api/routes.py and the /game Socket.IO namespace).

export interface Team {
  tid: string;
  name: string;
  score: number;
}

export interface QuestionState {
  answered: boolean;
  team_scores?: Record<string, number>;
}

export type QuestionsMap = Record<string, QuestionState>;

export interface AppConfig {
  NB_TEAMS?: number;
  MIN_TEAMS?: number;
  MAX_TEAMS?: number;
  VARIABLE_TEAMS?: boolean;
  CATEGORIES_PER_GAME?: number;
  MAX_ROUNDS?: number;
  QUESTIONS_PER_CATEGORY?: number;
  SCORE_TICK?: number;
  DAILYDOUBLE_WAIGER_MIN?: number;
  DAILYDOUBLE_WAIGER_MAX_MIN?: number;
}

export type GameState = "uninitialized" | "in_round" | "in_final" | "finished";

export interface UiState {
  question: string;
  team: string;
  dailydouble: "" | "enabled" | "revealed";
  message: string;
  "overlay-big": string;
  "overlay-small": string;
  "overlay-question": string;
  "container-header": string;
  "container-footer": string;
  [key: string]: string;
}

export interface ActiveQuestion {
  text?: string;
  category?: string;
  dailydouble?: boolean;
  // Jeopardy-style "correct question" for this clue (e.g. "What is
  // Paris?"). has_correct_response says whether one exists at all;
  // correct_response only shows up once the host reveals it.
  has_correct_response?: boolean;
  correct_response?: string;
}

export interface Range {
  min: number;
  max: number;
}

export interface DailyDoubleWager {
  team: string;
  amount: number;
}

export interface ServerMessage {
  id?: string;
  title?: string;
  text?: string;
}

// Final Jeopardy status. null when this round has no final question at all.
// Wager amounts are intentionally never included -- they only ever become
// visible (as a score change) once the host judges a team.
export interface FinalState {
  active: boolean;
  stage: "wager" | "revealed" | null;
  category?: string | null;
  wagered: string[];
  judged: string[];
}

// /api/v1/state payload (and the equivalent on the "state" socket event).
export interface ServerState {
  config?: AppConfig;
  game_state?: GameState;
  round?: number;
  teams?: Team[];
  categories?: string[];
  questions?: QuestionsMap;
  state?: Partial<UiState>;
  active_question?: ActiveQuestion | null;
  messages?: ServerMessage[];
  dailydouble_range?: Range;
  dailydouble_wager?: DailyDoubleWager | null;
  final?: FinalState | null;
}

// Socket event payloads (one per `s.on("...")` subscription in the store).
export interface QuestionShowEvent {
  qid: string;
  text: string;
  category: string;
  dailydouble: boolean;
  has_correct_response?: boolean;
}

export interface DailyDoubleEvent {
  qid: string;
  category: string;
  team?: string;
  range?: Range;
  has_correct_response?: boolean;
}

export interface DailyDoubleRevealEvent {
  qid: string;
  text: string;
  category: string;
}

export interface DailyDoubleRangeEvent {
  team?: string;
  range?: Range;
}

export interface DailyDoubleWagerEvent {
  team: string | null;
  amount: number | null;
}

export interface BoardUpdateEvent {
  questions: QuestionsMap;
  teams?: Team[];
}

export interface TeamSelectEvent {
  tid?: string | null;
}

export interface TeamRouletteEvent {
  sequence: string[];
  winner: string;
}

export interface TeamNamesEvent {
  names: Record<string, string>;
}

export interface OverlayBigEvent {
  html?: string;
  id?: string;
}

export interface SliderEvent {
  id: string;
  value: string | number;
}

export interface RedirectEvent {
  url?: string;
}

// REST request/response shapes.
export interface SubmitAnswerPayload {
  id: string;
  answers: Record<string, number>;
}

export interface SelectQuestionResponse {
  result?: string;
  dailydouble?: boolean;
  dailydouble_range?: Range;
  team?: string;
}

export interface InitPayload {
  action: "new" | string;
  nb_teams?: number;
  [key: string]: unknown;
}

export interface ApiOk {
  result?: string;
  [key: string]: unknown;
}
