<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<script setup lang="ts">
import { computed } from "vue";
import { useGameStore } from "@/stores/game";

const game = useGameStore();

// Show the clue overlay for normal questions, and for DDs once the operator
// has revealed the clue. Hidden during the DD wager phase.
const visible = computed(
  () =>
    !!game.activeQuestionId &&
    (!game.isDailyDouble || game.isDailyDoubleRevealed),
);
const html = computed(() => {
  let out = game.active_question?.text ?? "";
  if (game.active_question?.correct_response) {
    out += `<hr/>${game.active_question.correct_response}`;
  }
  return out;
});
</script>

<template>
  <Transition name="fade">
    <div v-if="visible" class="container-game container-absolute container-all">
      <div class="container-question-viewer">
        <div class="black-box flex-pad">
          <div class="container-question row-ceopardy flex-vertical-pad">
            <div class="col-ceopardy flex-horizontal-pad">
              <div class="box-ceopardy box-question-viewer" v-html="html" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>
