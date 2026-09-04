<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<script setup lang="ts">
import { computed } from "vue";
import { useGameStore } from "@/stores/game";
import TeamPanelViewer from "@/components/TeamPanelViewer.vue";

const game = useGameStore();

const rankedTeams = computed(() =>
  [...game.teams].sort((a, b) => b.score - a.score),
);
</script>

<template>
  <!-- Mirrors ViewerBoard's layout exactly (same three sections, same
       sizes, same blue boxes) so this reads as the same screen, not a
       different one -- just relabeled for the end of the game. -->
  <div class="container-game container-all container-light">
    <div class="container-categories-viewer">
      <div class="black-box flex-pad">
        <div class="row-ceopardy flex-vertical-pad" style="height: 100%">
          <div class="col-ceopardy flex-horizontal-pad">
            <div class="box-ceopardy box-category-viewer">
              <p>Final Scores</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="container-separator-h" />

    <div class="container-questions-viewer">
      <div class="black-box flex-pad">
        <div class="row-ceopardy flex-vertical-pad" style="height: 100%">
          <div class="col-ceopardy flex-horizontal-pad">
            <div class="box-ceopardy box-question-viewer">
              <p>Thanks for playing!</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="container-separator-h" />

    <!-- Same team cards, same 24% strip, as during play -- just ranked. -->
    <div class="container-results">
      <div
        v-for="(team, idx) in rankedTeams"
        :key="team.tid"
        class="container-team"
      >
        <TeamPanelViewer :team="team" :idx="idx" />
      </div>
    </div>
  </div>
</template>
