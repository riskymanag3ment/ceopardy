# Ceopardy

The Hacker Jeopardy Game Board we use at NorthSec.

**This is a customized fork of [obilodeau/ceopardy](https://github.com/obilodeau/ceopardy)**,
extended for self-hosting a full multi-round game night:

- Optional password protection on the host UI, and binding to any
  host/port (not just `127.0.0.1:5000`)
- Configurable team count (3–5) and 6 categories per game
- Multi-round play — Round 1 → Round 2 ("Double Jeopardy", 2x point
  values) → Final Jeopardy — with scores carrying over between rounds
- A full Final Jeopardy flow: category reveal, blind per-team wagers,
  question reveal, per-team judging, and a way to back out without
  ending the game
- CSV import: build a whole game (multiple rounds + an optional final
  question) from a spreadsheet instead of hand-editing text files
- Jeopardy-style "correct question" reveal: pair a clue with its
  expected response (`clue :: What is the answer?`) and reveal it with
  its own button, for normal questions, Daily Doubles, and Final
  Jeopardy alike
- A dedicated Final Scores screen for the crowd once the game ends

See [Features added in this fork](#features-added-in-this-fork) below for
details on each. Everything else — the core board, scoring, Daily
Doubles, buzzer support — works as documented upstream.

## Screenshots

This is what the crowd sees:

![The Viewer Interface Displaying the Game Board](docs/images/viewer-board.png)

When a clue is displayed:

![The Viewer Interface Displaying a Clue](docs/images/viewer-clue.png)

This is the host interface, how you control the game:

![The Host Interface](docs/images/host.png)

Note that there are two drawers that can be opened by clicking on the brown
arrows at the top and at the bottom of the screen. The top drawer contains
the functions to change team names. The bottom drawer provides functions to
display a custom message on the board or to pause a game.


## Architecture

Starting with v0.5, Ceopardy is split in two parts:

- A Python/Flask back-end that exposes a small REST API (`/api/v1/...`) and
  broadcasts state changes over a single Socket.IO namespace (`/game`).
- A Vite + Vue 3 + TypeScript front-end (in `frontend/`) that powers the
  crowd-facing viewer, the host UI, and the start screen.

Upstream Ceopardy is designed for single-operator local-network use: the
server binds to `127.0.0.1` and there is no authentication on the host UI.
**This fork adds `--host`/`--port` flags and an optional password gate**
(see below) so it can be exposed beyond localhost, but you're still
responsible for network-level access control (firewall / security group
rules) — the built-in auth is HTTP Basic over plain HTTP, not a substitute
for restricting who can reach the port at all.


## Running Ceopardy (operators)

This fork isn't published as a release wheel, so run it from a clone:

    git clone https://github.com/riskymanag3ment/ceopardy.git
    cd ceopardy
    make venv                          # creates .venv/ + installs deps
    source .venv/bin/activate          # bash/zsh
    npm --prefix frontend ci && npm --prefix frontend run build

Then scaffold a per-game directory and start the server:

    mkdir my-game && cd my-game
    ceopardy init               # writes data/ + game-media/ starter content
    # edit data/Questions.cp and data/1st.round, or import a CSV (see below)
    ceopardy serve                              # binds 127.0.0.1:5000, no auth
    ceopardy serve --host 0.0.0.0 --port 8080   # exposed beyond localhost
    ceopardy serve --debug                      # add verbose logging + auto-reload

Open the two URLs `ceopardy serve` prints:

- Viewer: `http://<host>:<port>/` — what the crowd sees on the projector.
- Host:   `http://<host>:<port>/host` — what you (the operator) drive.

`ceopardy init` never overwrites existing files; it's safe to re-run. The
SQLite database, round files, and uploaded media all resolve relative to the
directory you run `ceopardy` from, so **keep one directory per game**.

> **Note:** Ceopardy persists transactions to a SQLite database as the host
> submits points, so a crash doesn't lose the game state. The flipside is
> that games must be finalized (click "Finish") before a new one can be
> started in the same directory.

### Password-protecting the host UI

If you're binding beyond `127.0.0.1`, set a password before starting the
server:

    export CEOPARDY_HOST_PASSWORD='something-only-you-know'
    ceopardy serve --host 0.0.0.0 --port 8080

This gates `/host` and every state-changing `POST /api/v1/*` call behind
HTTP Basic Auth (any username, that password). The crowd-facing viewer and
read-only `GET` endpoints stay open, since the projector screen has no way
to enter credentials. Leave the variable unset to keep upstream's
no-auth behavior for local-only use. If `CEOPARDY_HOST_PASSWORD` is unset
and you bind to a non-loopback address, `ceopardy serve` prints a warning.


## Features added in this fork

### Variable team count & board size

`config.py` sets `MIN_TEAMS`/`MAX_TEAMS` (3–5, chosen per game at start)
and `CATEGORIES_PER_GAME` (6, up from upstream's 5).

### Multi-round play & Final Jeopardy

A round file can be one of a sequence: start a game on round 1, and once
its board is done, the host clicks **Next Round** (hidden once you've
reached `MAX_ROUNDS`, default 2) to load a second round's categories —
teams and scores carry over untouched, only the questions change. Round 2
values are automatically doubled (`SCORE_TICK * row * round_number`),
matching "Double Jeopardy."

A round file may declare a Final Jeopardy question:

    final: [Category Name] The clue text goes here

When the last round's board is finished, the host clicks **Start Final
Jeopardy**: the category is revealed to the crowd, each team enters a
wager (capped at their current score, floor 0), the host reveals the
question, then judges each team correct/incorrect — their locked-in wager
is added or subtracted automatically. Wager amounts are never broadcast to
the shared screen, only *whether* a team has wagered yet, so nothing leaks
before judging. A **Back to Board** action lets the host bail out of Final
Jeopardy without ending the game (e.g. started by mistake, or resuming
after a restart).

Finishing the game does not force any navigation — the host stays exactly
where they are (with a **Start a New Game** control replacing "Finish")
and the viewer switches to a **Final Scores** screen, in the same
categories/board/team-score layout as the live game, ranked highest to
lowest, until a new game starts.

### CSV import

From the "New Game" screen, a host can upload a spreadsheet instead of
hand-editing `Questions.cp`/`*.round` files. Download the in-app template,
fill it in, and upload:

    round,category,100,200,300,400,500
    1,Category A,clue,clue,clue,[dbl] clue,clue :: What is the answer?
    1,Category B,...                          (6 rows total for round 1)
    2,Category G,...                          (6 rows for round 2, optional)
    final,Final Category,Final clue :: What is the answer?

- One row per category; exactly `CATEGORIES_PER_GAME` rows per round.
- `[dbl]` prefix on a cell marks a Daily Double (same convention as the
  plain-text format).
- A `final` row (case-insensitive, at most one) is attached to the last
  round in the sheet.
- Category names must be unique across the whole sheet, even across
  different rounds.

Each import writes its own `data/<slug>-round<N>.round` +
`data/Questions-<slug>.cp` files — it never touches or collides with
hand-edited content, and re-uploading the same name replaces just that
question set. The New Game screen groups multi-round imports back into one
named entry (e.g. "Trivia Night (2 rounds)"); only the entry round is
offered there, since round 2+ is only reached via "Next Round" in-game.

### Answer/question reveal

Append `` :: `` and the expected response to any clue's text (in
`Questions.cp` lines or CSV cells) to give it a Jeopardy-style "correct
question":

    The capital of France :: What is Paris?
    [dbl] This element has the symbol Fe :: What is iron?

A **Reveal Question** button appears next to that clue, on both the host
and viewer screens, once it's on-screen — hidden again as soon as a
different question is selected. For a Daily Double, it only appears after
the clue itself has been revealed. Works the same way on the Final
Jeopardy question. A clue with no `::` in its text behaves exactly as
upstream (no button, nothing to reveal).

### Database migrations

Two features above added columns to the `question`/`game` tables
(`round`, `correct_response`... see `ceopardy/model.py`). `db.create_all()`
(run on every server start) only creates missing *tables*, not new
columns on existing ones — if you're upgrading an existing game directory
that already has a `ceopardy.db` predating this fork's schema, back it up
and run the equivalent `ALTER TABLE ... ADD COLUMN` manually, or just
start a fresh game directory.


## Hacking on Ceopardy (developers)

You need Python 3.11+, pip, virtualenv, and Node.js (LTS).

    git clone https://github.com/riskymanag3ment/ceopardy.git
    cd ceopardy
    make venv                          # creates .venv/ + installs deps
    source .venv/bin/activate          # bash/zsh
    source .venv/bin/activate.fish     # fish
    make init                          # seeds data/ + game-media/
    make run                           # starts Flask (:5000) + Vite (:5173)

Then open <http://localhost:5173/> — Vite hot-reloads the UI and proxies
`/api` and `/socket.io` to Flask on `:5000`. **In dev, always use the Vite
URL** (`:5173`); the Flask port serves the *built* SPA which gets stale.

### Optional: direnv

If you use [direnv](https://direnv.net/), the repo ships an `.envrc` that
auto-activates `.venv` on `cd`. Run `make venv` first (direnv won't), then
`direnv allow`.

### Before committing

Run the full CI suite — same checks GitHub Actions runs:

    make ci      # ruff lint + format check + prettier + vue-tsc + pytest

To auto-fix Python formatting first:

    make format

See `AGENTS.md` for the conventions the codebase follows.

### Building a wheel locally

`make build` reproduces the release path (frontend bundle + sdist + wheel):

    make build
    pipx install --force dist/ceopardy-*.whl   # test the wheel end-to-end
