<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api";
import { useGameStore } from "@/stores/game";

const router = useRouter();
const game = useGameStore();

const roundfiles = ref<string[]>([]);
const showRoundfiles = ref(false);
const mustInit = ref(true);

const minTeams = computed(() => game.config.MIN_TEAMS ?? 3);
const maxTeams = computed(() => game.config.MAX_TEAMS ?? 5);
const teamCountOptions = computed(() => {
  const options: number[] = [];
  for (let n = minTeams.value; n <= maxTeams.value; n++) options.push(n);
  return options;
});
const nbTeams = ref(game.config.NB_TEAMS ?? 3);

// Imported CSVs write one file per round ("<slug>-round1.round",
// "<slug>-round2.round", ...) so the game engine's existing round/next-round
// flow can drive them unchanged. For display+selection here they're grouped
// back into a single named entry -- the host picks a question SET, not an
// individual round file; round 2+ is only ever reached in-game via "Next
// Round". A hand-authored file with no "-round<N>" suffix is its own set.
interface RoundSet {
  label: string;
  startFile: string;
  roundCount: number;
}

const roundSets = computed<RoundSet[]>(() => {
  const multiRe = /^(.+)-round(\d+)\.round$/;
  const groups = new Map<string, number>();
  const sets: RoundSet[] = [];

  for (const f of roundfiles.value) {
    const m = f.match(multiRe);
    if (!m) {
      sets.push({ label: f, startFile: f, roundCount: 1 });
      continue;
    }
    const [, key, n] = m;
    groups.set(key, Math.max(groups.get(key) ?? 0, Number(n)));
  }
  for (const [key, roundCount] of groups) {
    const label = key
      .replace(/[-_]+/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
    sets.push({ label, startFile: `${key}-round1.round`, roundCount });
  }
  return sets;
});

onMounted(async () => {
  roundfiles.value = await api.roundfiles();
  // If a game has already been played the server lets us resume it.
  mustInit.value = !game.initialized
    ? true
    : game.game_state === "uninitialized";
  nbTeams.value = game.config.NB_TEAMS ?? 3;
});

async function startNew(filename: string): Promise<void> {
  await api.init({ action: "new", name: filename, nb_teams: nbTeams.value });
  await game.refresh();
  router.push({ name: "host" });
}

async function resume(): Promise<void> {
  await api.init({ action: "resume" });
  await game.refresh();
  router.push({ name: "host" });
}

// ---- Import questions from a spreadsheet (CSV) ----
// This is the source of truth for setting up a game's structure: how many
// rounds and whether there's a Final Jeopardy both come from the sheet
// itself (a "round" column per row, and an optional "final" row) rather
// than being chosen separately in the UI.
const importName = ref("");
const importFile = ref<File | null>(null);
const importError = ref("");
const importSuccess = ref("");
const importing = ref(false);

function onImportFileChange(e: Event): void {
  const input = e.target as HTMLInputElement;
  importFile.value = input.files?.[0] ?? null;
}

async function doImport(): Promise<void> {
  importError.value = "";
  importSuccess.value = "";
  if (!importName.value.trim() || !importFile.value) {
    importError.value = "Enter a name and choose a CSV file.";
    return;
  }
  importing.value = true;
  try {
    const res = await api.importRoundfile(
      importName.value.trim(),
      importFile.value,
    );
    const n = res.roundfiles?.length ?? 1;
    importSuccess.value = `Imported "${importName.value.trim()}" (${n} round${n === 1 ? "" : "s"}). Pick it below to start.`;
    importName.value = "";
    importFile.value = null;
    roundfiles.value = await api.roundfiles();
  } catch (e) {
    importError.value = e instanceof Error ? e.message : String(e);
  } finally {
    importing.value = false;
  }
}

// Client-side CSV template so a non-technical host can open it directly in
// Google Sheets/Excel, fill it in, and re-export as CSV to upload above.
function downloadTemplate(): void {
  const cats = game.config.CATEGORIES_PER_GAME ?? 6;
  const qs = game.config.QUESTIONS_PER_CATEGORY ?? 5;
  const tick = game.scoreTick;
  const header = [
    "round",
    "category",
    ...Array.from({ length: qs }, (_, i) => String((i + 1) * tick)),
  ];
  const rows = [header];
  for (const round of [1, 2]) {
    for (let c = 1; c <= cats; c++) {
      rows.push([
        String(round),
        `Round ${round} Category ${c}`,
        ...Array.from(
          { length: qs },
          (_, q) => `Question ${q + 1} :: What is the answer?`,
        ),
      ]);
    }
  }
  rows.push([
    "final",
    "Final Category",
    "Final question text :: What is the answer?",
  ]);
  const csv = rows
    .map((r) => r.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(","))
    .join("\r\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "ceopardy-template.csv";
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="start-container container-light">
    <div style="flex-grow: 1" />
    <div class="start-title">Ceopardy!</div>

    <div class="start-menu">
      <i class="fa-solid fa-arrow-right animate-horizontal-right" />
      <a @click="showRoundfiles = !showRoundfiles">New Game</a>
      <i class="fa-solid fa-arrow-left animate-horizontal-left" />
    </div>

    <div
      v-if="showRoundfiles"
      class="black-box flex-small-pad"
      style="padding: 14px; color: #d5c19c; max-width: 480px; text-align: left"
    >
      <p style="margin: 0 0 8px">
        <b>Add questions:</b> download the template, fill it in with your
        categories and questions in Google Sheets/Excel (a "round" column lets
        you lay out multiple rounds, plus an optional Final Jeopardy row),
        export as CSV, then upload it here. Add
        <code>:: What is the answer?</code> after a clue to give it a
        Jeopardy-style correct question, revealed with its own button during
        play.
      </p>
      <button type="button" @click="downloadTemplate">
        Download template CSV
      </button>

      <div style="margin-top: 12px">
        <label style="display: block; margin-bottom: 6px">
          Name:
          <input
            v-model="importName"
            type="text"
            placeholder="e.g. Community Night"
            style="margin-left: 6px"
          />
        </label>
        <label style="display: block; margin-bottom: 6px">
          CSV file:
          <input type="file" accept=".csv" @change="onImportFileChange" />
        </label>
        <button type="button" :disabled="importing" @click="doImport">
          {{ importing ? "Importing..." : "Upload" }}
        </button>
      </div>

      <p v-if="importError" style="color: #e05353; margin-top: 8px">
        {{ importError }}
      </p>
      <p v-if="importSuccess" style="color: #4caf50; margin-top: 8px">
        {{ importSuccess }}
      </p>

      <hr style="margin: 14px 0; border-color: #d5c19c44" />

      <p style="margin: 0 0 8px"><b>Start a game:</b></p>
      <div style="margin-bottom: 10px">
        Teams:
        <label v-for="n in teamCountOptions" :key="n" style="margin: 0 6px">
          <input type="radio" :value="n" v-model="nbTeams" />
          {{ n }}
        </label>
      </div>
      <template v-for="(set, i) in roundSets" :key="set.startFile">
        <span v-if="i > 0"> · </span>
        <a
          style="cursor: pointer; color: #d5c19c; text-decoration: underline"
          @click="startNew(set.startFile)"
          >{{ set.label }}
          <span v-if="set.roundCount > 1"
            >({{ set.roundCount }} rounds)</span
          ></a
        >
      </template>
      <div v-if="roundSets.length === 0" style="margin-top: 10px">
        No questions imported yet -- add some above.
      </div>
    </div>

    <div v-if="!mustInit && game.game_state === 'finished'" class="start-menu">
      <i class="fa-solid fa-rotate-left" />
      <a @click="resume">Resume Last Game</a>
    </div>

    <div style="flex-grow: 1" />
  </div>
</template>
