<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api";
import { useGameStore } from "@/stores/game";

import HostBoard from "@/components/HostBoard.vue";
import HostControls from "@/components/HostControls.vue";
import HostHeaderDrawer from "@/components/HostHeaderDrawer.vue";
import HostFooterDrawer from "@/components/HostFooterDrawer.vue";
import TeamScoringPanel from "@/components/TeamScoringPanel.vue";

type AnswerMap = Record<string, number>;
type SoundName =
  | "buzzer1"
  | "buzzer2"
  | "buzzer3"
  | "timeout"
  | "reveal"
  | "thinking"
  | "dailydouble";

const router = useRouter();
const game = useGameStore();

// Local form state for the per-team answer sliders.
const answers = ref<AnswerMap>({});

function resetAnswers(): void {
  const next: AnswerMap = {};
  for (const t of game.teams) next[t.tid] = 0;
  answers.value = next;
}

onMounted(async () => {
  game.isHost = true;
  if (!game.initialized) await game.refresh();
  if (!game.isInProgress) {
    router.push({ name: "start" });
    return;
  }
  resetAnswers();
});

// Whenever a new question gets selected, reset the slider values so we don't
// carry state from a previous question.
watch(
  () => game.activeQuestionId,
  (qid, oldQid) => {
    if (qid !== oldQid) resetAnswers();
  },
);

// ---- Buzzer handling ----
const buzzersLocked = ref(true);
function toggleBuzzers(): void {
  buzzersLocked.value = !buzzersLocked.value;
}
function lockBuzzers(): void {
  buzzersLocked.value = true;
}
function unlockBuzzers(): void {
  buzzersLocked.value = false;
}

// Keyboard events from the emulated-keyboard buzzers.
function onKeyPress(e: KeyboardEvent): void {
  if (buzzersLocked.value) return;
  // Only numeric keys 1..N.
  const num = parseInt(e.key, 10);
  if (!Number.isInteger(num)) return;
  if (num < 1 || num > game.teams.length) return;
  const tid = `team${num}`;
  api.selectTeam(tid);
  playSound(`buzzer${num}` as SoundName);
  lockBuzzers();
}

onMounted(() => {
  window.addEventListener("keypress", onKeyPress);
});

// ---- Question selection ----
async function onSelectQuestion(qid: string): Promise<void> {
  if (finalActive.value) return;
  if (game.activeQuestionId === qid) {
    await api.deselectQuestion();
    lockBuzzers();
    game.hostAnswerPreview = null;
    return;
  }
  game.hostAnswerPreview = null; // clear the previous clue's answer immediately
  const data = await api.selectQuestion(qid);
  if (data?.dailydouble) {
    if (data.dailydouble_range) game.dailydouble_range = data.dailydouble_range;
    if (data.team) game.ui_state.team = data.team;
    // No buzzer race in a Daily Double — only the controlling team plays.
    lockBuzzers();
    playSound("dailydouble");
    // The DD clue (and its answer) aren't shown until "Reveal clue" --
    // hostAnswerPreview is set there instead, once the clue itself is up.
  } else {
    unlockBuzzers();
    if (data?.correct_response) game.hostAnswerPreview = data.correct_response;
  }
}

// ---- Submitting answers ----
async function submitAnswers(): Promise<void> {
  if (!game.activeQuestionId) return;
  const payload = { id: game.activeQuestionId, answers: answers.value };
  const res = await api.submitAnswer(payload);
  if (res?.result === "success") {
    await api.deselectQuestion();
    lockBuzzers();
  }
}

// ---- Next round ----
// Capped at MAX_ROUNDS (2: Round 1 + "Double Jeopardy") -- past that, the
// only ways forward are Final Jeopardy or Finish.
const maxRounds = computed(() => game.config.MAX_ROUNDS ?? 2);
const showNextRound = computed(
  () => !game.isFinished && game.round < maxRounds.value,
);
const showRoundPicker = ref(false);
const roundfiles = ref<string[]>([]);
async function onNextRound(): Promise<void> {
  if (!showNextRound.value) return;
  showRoundPicker.value = !showRoundPicker.value;
  if (showRoundPicker.value) roundfiles.value = await api.roundfiles();
}
async function startNextRound(filename: string): Promise<void> {
  if (
    !window.confirm(
      `Start next round with "${filename}"? Teams and scores carry over.`,
    )
  ) {
    return;
  }
  await api.nextRound(filename);
  await game.refresh();
  showRoundPicker.value = false;
}

// ---- Final Jeopardy ----
const showFinalStart = computed(
  () => !game.isFinished && game.final !== null && !game.final.active,
);
const finalActive = computed(() => game.final?.active === true);
async function onFinalStart(): Promise<void> {
  if (
    !window.confirm(
      "Start Final Jeopardy? This reveals the category and opens wagers.",
    )
  ) {
    return;
  }
  await api.finalStart();
  await game.refresh();
}
async function onFinalCancel(): Promise<void> {
  if (
    !window.confirm(
      "Back out of Final Jeopardy and return to the board? This does not end the game -- you can start Final Jeopardy again later.",
    )
  ) {
    return;
  }
  await api.finalCancel();
  await game.refresh();
}
async function onFinalReveal(): Promise<void> {
  await api.finalReveal();
  await game.refresh();
}

// ---- Roulette / finish / sounds ----
function onRoulette(): void {
  api.roulette();
}
// Finishing intentionally does NOT navigate anywhere -- the host stays on
// this screen with the final scores up (team score badges + the "That's all
// folks!" overlay) until they deliberately choose to start a new game.
async function onFinish(): Promise<void> {
  if (window.confirm("End the game and show final scores. Are you sure?")) {
    await api.finish();
    await game.refresh();
  }
}
function goToStart(): void {
  router.push({ name: "start" });
}
function playTimeout(): void {
  playSound("timeout");
}

const soundUrls: Record<SoundName, string> = {
  buzzer1: "/static/sounds/buzzer1.wav",
  buzzer2: "/static/sounds/buzzer2.wav",
  buzzer3: "/static/sounds/buzzer3.wav",
  timeout: "/static/sounds/timeout.mp3",
  reveal: "/static/sounds/reveal.mp3",
  thinking: "/static/sounds/thinking-music.wav",
  dailydouble: "/static/sounds/daily-double.mp3",
};
const preloaded: Partial<Record<SoundName, HTMLAudioElement>> = {};
for (const [name, url] of Object.entries(soundUrls) as [SoundName, string][]) {
  const a = new Audio(url);
  a.preload = "auto";
  preloaded[name] = a;
}

let thinkingAudio: HTMLAudioElement | null = null;
function playSound(name: SoundName): void {
  try {
    const audio = new Audio(soundUrls[name]);
    audio.play().catch(() => {});
  } catch {
    /* ignore */
  }
}
function toggleThinking(): void {
  if (thinkingAudio && !thinkingAudio.paused) {
    thinkingAudio.pause();
    thinkingAudio.currentTime = 0;
    thinkingAudio = null;
  } else {
    thinkingAudio = new Audio(soundUrls.thinking);
    thinkingAudio.play().catch(() => {});
  }
}

// Automatically unlock buzzers if any team is marked "Bad" so it can buzz in
// again.
watch(
  answers,
  (val) => {
    for (const t of game.teams) {
      if (val[t.tid] === -1) {
        unlockBuzzers();
        break;
      }
    }
  },
  { deep: true },
);

const activeHtml = computed(() => {
  // During Final Jeopardy, the standard preview box shows the same
  // category/question HTML the viewer's big overlay is showing.
  if (finalActive.value) return game.bigOverlayHtml;
  if (game.isDailyDouble && !game.isDailyDoubleRevealed) {
    return "<p>Daily Double!<br/>Please input user bet.</p>";
  }
  // Revealed to everyone: only the answer, nothing else.
  if (game.active_question?.correct_response) {
    return game.active_question.correct_response;
  }
  const clue = game.active_question?.text ?? "";
  // Host-only, always-visible answer preview -- known before anyone else
  // sees it, shown clearly separated from the clue so it's easy to read.
  if (!game.hostAnswerPreview) return clue;
  return (
    `<div class="host-clue-answer-wrap">` +
    `<div class="host-clue-text">${clue}</div>` +
    `<div class="host-answer-block">` +
    `<span class="host-answer-label">Answer</span>` +
    `${game.hostAnswerPreview}` +
    `</div>` +
    `</div>`
  );
});

const canRevealDailyDouble = computed(
  () =>
    game.isDailyDouble &&
    !game.isDailyDoubleRevealed &&
    game.dailydouble_wager != null,
);

const canRevealFinal = computed(() => game.final?.stage === "wager");

// Eye icon: shown once the host knows the answer and it hasn't been
// revealed to everyone yet.
const canRevealAnswer = computed(
  () => !!game.hostAnswerPreview && !game.active_question?.correct_response,
);

async function onRevealDailyDouble(): Promise<void> {
  const data = await api.revealDailyDouble();
  if (data?.correct_response) game.hostAnswerPreview = data.correct_response;
}

async function onRevealAnswer(): Promise<void> {
  await api.revealAnswer();
}
</script>

<template>
  <div class="container-host">
    <HostHeaderDrawer />

    <!-- Spacer for the top arrow -->
    <div class="container-all container-light" style="height: 35px" />

    <HostBoard @select="onSelectQuestion" />

    <div class="container-bottom container-all container-light">
      <HostControls
        :buzzers-locked="buzzersLocked"
        :show-next-round="showNextRound"
        :show-final-start="showFinalStart"
        :show-final-cancel="finalActive"
        :show-new-game="game.isFinished"
        @roulette="onRoulette"
        @timeout="playTimeout"
        @thinking="toggleThinking"
        @toggle-buzzers="toggleBuzzers"
        @submit="submitAnswers"
        @next-round="onNextRound"
        @final-start="onFinalStart"
        @final-cancel="onFinalCancel"
        @finish="onFinish"
        @new-game="goToStart"
      />

      <div
        v-if="showRoundPicker"
        class="black-box flex-small-pad"
        style="position: absolute; z-index: 10; padding: 10px; color: #d5c19c"
      >
        <p style="margin: 0 0 8px">
          Start next round (teams/scores carry over):
        </p>
        <template v-for="(file, i) in roundfiles" :key="file">
          <span v-if="i > 0"> · </span>
          <a
            style="cursor: pointer; color: #d5c19c; text-decoration: underline"
            @click="startNextRound(file)"
            >{{ file }}</a
          >
        </template>
        <div v-if="roundfiles.length === 0" style="margin-top: 6px">
          No round files found in <code>data/</code>.
        </div>
      </div>

      <form class="container-bottom-middle" @submit.prevent="submitAnswers">
        <TeamScoringPanel
          v-for="(team, idx) in game.teams"
          :key="team.tid"
          :team="team"
          :idx="idx"
          :answers="answers"
          @update:answers="answers = $event"
        />
      </form>

      <div class="container-bottom-right">
        <div class="black-box flex-small-pad">
          <div class="box-fake-overlay">
            <div class="box-ceopardy box-question-host" v-html="activeHtml" />
            <button
              v-if="canRevealDailyDouble"
              type="button"
              class="dd-reveal-btn"
              @click="onRevealDailyDouble"
            >
              <i class="fa-solid fa-eye" /> Reveal clue
            </button>
            <button
              v-if="canRevealAnswer"
              type="button"
              class="eye-reveal-icon"
              title="Reveal the answer to everyone"
              @click="onRevealAnswer"
            >
              <i class="fa-solid fa-eye" />
            </button>
            <button
              v-if="canRevealFinal"
              type="button"
              class="dd-reveal-btn"
              @click="onFinalReveal"
            >
              <i class="fa-solid fa-eye" /> Reveal Question
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="container-all container-light" style="height: 35px" />

    <HostFooterDrawer />
  </div>
</template>
