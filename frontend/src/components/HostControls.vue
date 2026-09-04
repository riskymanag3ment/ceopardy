<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<script setup lang="ts">
import { ref } from "vue";

const props = withDefaults(
  defineProps<{
    buzzersLocked?: boolean;
    showNextRound?: boolean;
    showFinalStart?: boolean;
    showFinalCancel?: boolean;
    showNewGame?: boolean;
  }>(),
  {
    buzzersLocked: true,
    showNextRound: false,
    showFinalStart: false,
    showFinalCancel: false,
    showNewGame: false,
  },
);
const emit = defineEmits<{
  (e: "roulette"): void;
  (e: "timeout"): void;
  (e: "thinking"): void;
  (e: "toggle-buzzers"): void;
  (e: "submit"): void;
  (e: "next-round"): void;
  (e: "final-start"): void;
  (e: "final-cancel"): void;
  (e: "finish"): void;
  (e: "new-game"): void;
}>();
const spinning = ref(false);
function hoverSpinner(state: boolean): void {
  spinning.value = state;
}
</script>

<template>
  <div class="container-bottom-left">
    <div class="black-box flex-small-pad">
      <div class="box-fake-overlay">
        <div class="box-ceopardy">
          <div class="container-controls form-color">
            <div
              class="form-icon form-click"
              title="Random team pick"
              @click="emit('roulette')"
              @mouseenter="hoverSpinner(true)"
              @mouseleave="hoverSpinner(false)"
            >
              <i
                class="fa-solid fa-arrows-spin fa-2x fa-fw"
                :class="{ 'fa-spin': spinning }"
              />
            </div>
            <div
              class="form-icon form-click"
              title="Timeout sound"
              @click="emit('timeout')"
            >
              <i class="fa-regular fa-clock fa-2x" />
            </div>
            <div
              class="form-icon form-click"
              title="Thinking music"
              @click="emit('thinking')"
            >
              <i class="fa-solid fa-music fa-2x" />
            </div>
            <div
              class="form-icon form-click"
              title="Lock / unlock buzzers"
              @click="emit('toggle-buzzers')"
            >
              <i
                class="fa-solid fa-2x fa-fw"
                :class="props.buzzersLocked ? 'fa-lock' : 'fa-lock-open'"
              />
            </div>
            <div
              class="form-icon form-click"
              title="Submit score"
              @click="emit('submit')"
            >
              <i class="fa-regular fa-square-check fa-2x" />
            </div>
            <div
              v-if="props.showNextRound"
              class="form-icon form-click"
              title="Start next round (keeps teams and scores)"
              @click="emit('next-round')"
            >
              <i class="fa-solid fa-forward fa-2x" />
            </div>
            <div
              v-if="props.showFinalStart"
              class="form-icon form-click"
              title="Start Final Jeopardy (wagers, then the question)"
              @click="emit('final-start')"
            >
              <i class="fa-solid fa-star fa-2x" />
            </div>
            <div
              v-if="props.showFinalCancel"
              class="form-icon form-click"
              title="Back out of Final Jeopardy (does not end the game)"
              @click="emit('final-cancel')"
            >
              <i class="fa-solid fa-rotate-left fa-2x" />
            </div>
            <div
              v-if="!props.showNewGame"
              class="form-icon form-click"
              title="Finish the game"
              @click="emit('finish')"
            >
              <i class="fa-solid fa-right-from-bracket fa-2x" />
            </div>
            <div
              v-if="props.showNewGame"
              class="form-icon form-click"
              title="Start a new game"
              @click="emit('new-game')"
            >
              <i class="fa-solid fa-flag-checkered fa-2x" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
