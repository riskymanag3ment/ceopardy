# Ceopardy
# https://github.com/obilodeau/ceopardy/
#
# Olivier Bilodeau <olivier@bottomlesspit.org>
# Copyright (C) 2017, 2019, 2024, 2026 Olivier Bilodeau
# All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
import json
import os
import re
from collections import OrderedDict
from datetime import datetime

from flask import current_app as app
from sqlalchemy import and_

from ceopardy import db
from ceopardy.config import config
from ceopardy.exceptions import GameProblem, UnknownTeamError
from ceopardy.model import (
    Answer,
    FinalQuestion,
    Game,
    GameState,
    Question,
    Response,
    State,
    Team,
)
from ceopardy.utils import (
    parse_gamefile,
    parse_question_id,
    parse_questions,
    question_to_html,
)


class Controller:
    def __init__(self):
        Controller._init()

    @staticmethod
    def _init():
        """
        This was extracted away from __init__ because it is called on a game
        reset which happens in a static method.
        """

        # If there's not a game state, create one
        if Game.query.one_or_none() is None:
            game = Game()
            db.session.add(game)
            # Default overlay state for a new game
            db.session.add(State("overlay-small", ""))
            db.session.add(
                State("overlay-big", "<p>There is currently no host running the show!</p>")
            )
            # No question is selected, the game hasn't started
            db.session.add(State("question", ""))
            db.session.add(State("container-header", "slide-down"))
            db.session.add(State("container-footer", "slide-up"))
            db.session.commit()

    @staticmethod
    def is_game_in_progress():
        game = Game.query.one()
        return game.state == GameState.in_round or game.state == GameState.in_final

    @staticmethod
    def is_game_initialized():
        game = Game.query.one()
        return game.state != GameState.uninitialized

    @staticmethod
    def setup_teams(teamnames):
        """Teamnames is {teamid: team_name} dict"""
        app.logger.info("Setup teams: {}".format(teamnames))
        game = Game.query.one()
        if game.state == GameState.uninitialized:
            for _tid, _tn in teamnames.items():
                team = Team(_tid, _tn)
                db.session.add(team)
            db.session.commit()
        else:
            raise GameProblem("Trying to setup a game that is already started")
        return True

    @staticmethod
    def update_teams(teamnames):
        """Teamnames is {teamid: team_name} dict"""
        app.logger.info("Update teams: {}".format(teamnames))
        for _id, _name in teamnames.items():
            db.session.query(Team).filter_by(tid=_id).update({"name": _name})
        db.session.commit()

    @staticmethod
    def setup_questions(round_file, q_file=config["QUESTIONS_FILENAME"], round_number=1):
        app.logger.info("Setup questions from file: {} (round {})".format(q_file, round_number))
        game = Game.query.one()
        if round_number == 1:
            if game.state != GameState.uninitialized:
                raise GameProblem("Trying to setup a game that is already started")
        else:
            if game.state != GameState.in_round:
                raise GameProblem("Trying to start a next round when no round is in progress")

        # CSV-imported rounds get their own dedicated questions file
        # (data/Questions-<slug>.cp) instead of sharing the default one, so
        # importing never collides with hand-edited content. A multi-round
        # import shares one such file across "<slug>-round1.round",
        # "<slug>-round2.round", etc., so the "-round<N>" suffix is
        # stripped before deriving the shared filename. Detected purely by
        # convention so callers (/init, next_round) need no changes.
        if q_file == config["QUESTIONS_FILENAME"]:
            stem = round_file.rsplit(".", 1)[0]
            base_stem = re.sub(r"-round\d+$", "", stem)
            candidate = "data/Questions-{}.cp".format(base_stem)
            if os.path.exists(config["BASE_DIR"] + candidate):
                q_file = candidate

        gamefile, final = parse_gamefile(config["BASE_DIR"] + "data/" + round_file)
        questions = parse_questions(config["BASE_DIR"] + q_file)

        # TODO do some validation based on config constants
        for _col, _cat in enumerate(gamefile, start=1):
            for _row, _q in enumerate(questions[_cat], start=1):
                # Each round's values scale with its number (round 2 =
                # "Double Jeopardy" = 2x round 1, matching the real show).
                score = _row * config["SCORE_TICK"] * round_number

                daily_double = False
                if _q.startswith("[dbl]"):
                    _q = _q.lstrip("[dbl]").lstrip()
                    daily_double = True

                # Optional "<clue> :: <correct question>" split, e.g.
                # "The capital of France :: What is Paris?" -- the part
                # after "::" is hidden until the host reveals it.
                correct_response = ""
                if "::" in _q:
                    _q, correct_response = _q.split("::", 1)
                    _q = _q.strip()
                    correct_response = correct_response.strip()

                question = Question(
                    _q,
                    score,
                    _cat,
                    _row,
                    _col,
                    double=daily_double,
                    round=round_number,
                    correct_response=correct_response,
                )
                db.session.add(question)

        # Add final question
        if final is not None:
            final = FinalQuestion(**final)
            final_text = final.question
            final_response = ""
            if "::" in final_text:
                final_text, final_response = final_text.split("::", 1)
                final_text = final_text.strip()
                final_response = final_response.strip()
            question = Question(
                final_text,
                0,
                final.category,
                0,
                0,
                final=True,
                round=round_number,
                correct_response=final_response,
            )
            db.session.add(question)

        # Once everything loaded successfully, identify round file and commit
        game.round_filename = round_file
        game.current_round = round_number
        db.session.add(game)
        db.session.commit()
        return True

    @staticmethod
    def get_current_round():
        return Game.query.one().current_round or 1

    @staticmethod
    def start_next_round(round_file):
        """Load a new round's questions while keeping teams and cumulative
        scores intact (unlike a brand new game, nothing is wiped)."""
        game = Game.query.one()
        if game.state != GameState.in_round:
            raise GameProblem("Trying to start a next round when no round is in progress")
        current_round = game.current_round or 1
        if current_round >= config["MAX_ROUNDS"]:
            raise GameProblem(
                f"Already at the last round ({config['MAX_ROUNDS']}); "
                "start Final Jeopardy or finish the game instead"
            )

        next_round = current_round + 1
        Controller.setup_questions(round_file, round_number=next_round)

        # Reset per-round UI state so the new board starts clean.
        Controller.set_state("question", "")
        Controller.end_dailydouble()
        Controller.end_final()
        Controller.set_state("team", "")
        return True

    @staticmethod
    def start_game():
        app.logger.info("Starting the game. Good luck everyone!")
        # Are there teams and questions?
        if Team.query.all() and Question.query.all():
            # Yes, mark game as started
            game = Game.query.one()
            game.state = GameState.in_round
            db.session.commit()
            return True

        else:
            raise GameProblem("Trying to start a game that is not ready")

    @staticmethod
    def finish_game():
        scores = Controller.get_teams_score()
        app.logger.info("Game is finished. Teams / Scores: {}".format(scores))

        # Mark as finished
        game = Game.query.one()
        game.state = GameState.finished
        db.session.commit()
        return True

    @staticmethod
    def resume_game():
        """Resuming a game is simply allowing to start over a finished game.

        Sometimes people click on finish by mistake or mess-up the score
        in the final round. Resuming a game enables to fix that.
        """
        if Controller.is_game_initialized() is False:
            app.logger.warn("Attempting to resume an uninitialized game...")
            return False

        game = Game.query.one()
        game.state = GameState.in_round
        db.session.commit()
        scores = Controller.get_teams_score()
        app.logger.info("A game has been resumed. Current teams / scores: {}".format(scores))
        return True

    @staticmethod
    def get_config():
        return config

    @staticmethod
    def get_teams_score():
        if Controller.is_game_initialized():
            answers = (
                db.session.query(Team.id, Team.name, Answer.response, Answer.score_attributed)
                .join(Answer)
                .order_by(Team.id)
                .all()
            )

            results = OrderedDict()
            # Handle case when there are no answers: names with 0 score
            if not answers:
                for _team in db.session.query(Team).order_by(Team.id).all():
                    results[_team.name] = 0
                return results

            # Sum all answers with negative scoring handled for bad answers
            for answer in answers:
                _id, _name, _response, _score = answer
                # Not already defined? initialize
                if not results.get(_name):
                    results[_name] = 0

                # bad: -1, nop: 0 and good: 1 multiplied with score gives result
                results[_name] += _response.value * _score
            return results

        else:
            # Return names with a 0 score
            return {name: 0 for tid, name in Controller.get_teams_for_form().items()}

    # TODO remove
    # Temporary fix, find a way to merge with the function above!
    @staticmethod
    def get_teams_score_by_tid():
        answers = (
            db.session.query(Team.id, Team.tid, Answer.response, Answer.score_attributed)
            .join(Answer)
            .order_by(Team.id)
            .all()
        )

        results = OrderedDict()
        # Handle case when there are no answers: names with 0 score
        if not answers:
            for _team in db.session.query(Team).order_by(Team.id).all():
                results[_team.tid] = 0
            return results

        # Sum all answers with negative scoring handled for bad answers
        for answer in answers:
            _id, _tid, _response, _score = answer
            # Not already defined? initialize
            if not results.get(_tid):
                results[_tid] = 0

            # bad: -1, nop: 0 and good: 1 multiplied with score gives result
            results[_tid] += _response.value * _score
        return results

    @staticmethod
    def get_good_answer_team(col, row):
        """
        Returns the team id of the team who correctly answered the specified question
        """
        team = (
            db.session.query(Team)
            .join(Answer)
            .join(Question)
            .filter(
                and_(Question.col == col, Question.row == row, Answer.response == Response.good)
            )
            .first()
        )
        if team:
            return team.tid
        else:
            None

    @staticmethod
    def get_teams_for_form():
        """Get list of teams
        If there are no teams, then return place holder teams. This is useful
        to render template for game setup."""
        if Team.query.first() is not None:
            return {team.tid: team.name for team in Team.query.all()}
        else:
            return {
                "team{}".format(_i): "Team {}".format(_i) for _i in range(1, config["NB_TEAMS"] + 1)
            }

    @staticmethod
    def get_team_in_control():
        return Team.query.filter(Team.tid == Controller.get_state("team")).one()

    @staticmethod
    def get_dailydouble_waiger_range(team_id):
        _min = config.get("DAILYDOUBLE_WAIGER_MIN")
        scores = Controller.get_teams_score_by_tid()
        try:
            _max = scores[team_id]
        except KeyError as e:
            raise UnknownTeamError(f"Unknown team {team_id!r}") from e
        if _max < config.get("DAILYDOUBLE_WAIGER_MAX_MIN"):
            _max = config.get("DAILYDOUBLE_WAIGER_MAX_MIN")
        return (_min, _max)

    @staticmethod
    def set_dailydouble_wager(tid: str, amount: int) -> tuple[str, int]:
        """Validate and persist the DD wager for the controlling team."""
        _min, _max = Controller.get_dailydouble_waiger_range(tid)
        if not (_min <= amount <= _max):
            raise GameProblem(f"Wager {amount} outside [{_min}, {_max}] for {tid}")
        Controller.set_state("dailydouble-wager", f"{tid}:{amount}")
        return tid, amount

    @staticmethod
    def get_dailydouble_wager() -> tuple[str, int] | None:
        """Return the persisted (tid, amount) wager, or None."""
        raw = Controller.get_state("dailydouble-wager") or ""
        if ":" not in raw:
            return None
        tid, amount = raw.split(":", 1)
        try:
            return tid, int(amount)
        except ValueError:
            return None

    @staticmethod
    def clear_dailydouble_wager() -> None:
        Controller.set_state("dailydouble-wager", "")

    @staticmethod
    def end_dailydouble() -> None:
        """Turn DD off and clear any wager. Use everywhere DD ends."""
        Controller.set_state("dailydouble", "")
        Controller.clear_dailydouble_wager()

    @staticmethod
    def teams_exists():
        if Team.query.all():
            return True
        return False

    @staticmethod
    def get_nb_teams():
        return Team.query.count() or config["NB_TEAMS"]

    @staticmethod
    def get_categories():
        return [
            _q.category
            for _q in db.session.query(Question.category)
            .distinct()
            .filter(Question.final == False, Question.round == Controller.get_current_round())  # noqa: E712
            .order_by(Question.col)
        ]

    @staticmethod
    def get_question(column, row):
        app.logger.info("Question requested for row: {} and col: {}".format(row, column))

        condition = and_(
            Question.row == row,
            Question.col == column,
            Question.round == Controller.get_current_round(),
        )
        _q = Question.query.filter(condition).one()
        return {
            "text": question_to_html(_q.text),
            "category": _q.category,
            "dailydouble": _q.double,
            "has_correct_response": bool(_q.correct_response),
        }

    @staticmethod
    def get_correct_response(column, row):
        """The Jeopardy-style correct question for a clue, or "" if unset."""
        condition = and_(
            Question.row == row,
            Question.col == column,
            Question.round == Controller.get_current_round(),
        )
        _q = Question.query.filter(condition).one()
        return question_to_html(_q.correct_response) if _q.correct_response else ""

    @staticmethod
    def reveal_correct_response():
        """Reveal the active clue's correct question, e.g. after the host
        judges an answer. No-op-safe: raises if there's nothing to reveal."""
        qid = Controller.get_complete_state().get("question", "")
        if not qid:
            raise GameProblem("No active question")
        col, row = parse_question_id(qid)
        response = Controller.get_correct_response(col, row)
        if not response:
            raise GameProblem("This question has no correct response set")
        Controller.set_state("answer-revealed", "true")
        return response

    @staticmethod
    def get_active_question():
        _q = {}
        qid = Controller.get_complete_state().get("question", "")
        if qid != "":
            col, row = parse_question_id(qid)
            _q = Controller.get_question(col, row)
            if Controller.get_state("answer-revealed") == "true":
                _q["correct_response"] = Controller.get_correct_response(col, row)
        return _q

    @staticmethod
    def is_final_question():
        """Is there a final question for this game?"""
        condition = and_(Question.final == True, Question.round == Controller.get_current_round())  # noqa: E712
        return Question.query.filter(condition).one_or_none() is not None

    @staticmethod
    def get_final_question():
        """The Question row for this round's Final Jeopardy, or None."""
        condition = and_(Question.final == True, Question.round == Controller.get_current_round())  # noqa: E712
        return Question.query.filter(condition).one_or_none()

    @staticmethod
    def get_final_question_payload():
        q = Controller.get_final_question()
        if q is None:
            return None
        return {"category": q.category, "text": question_to_html(q.text)}

    @staticmethod
    def start_final_round():
        """Enter Final Jeopardy: reveal the category, open wagers, keep the
        question itself hidden until reveal_final_question()."""
        if not Controller.is_final_question():
            raise GameProblem("No final question configured for this round")
        game = Game.query.one()
        if game.state != GameState.in_round:
            raise GameProblem("Trying to start Final Jeopardy when no round is in progress")
        game.state = GameState.in_final
        db.session.commit()
        Controller.set_state("final", "wager")
        Controller.set_state("final-wagers", "{}")
        return True

    @staticmethod
    def get_final_wager_range(tid):
        """A team may wager anywhere from 0 up to its current score (teams
        at 0 or below can only wager 0, same rule as broadcast Jeopardy).

        Note: get_teams_score_by_tid() only has entries for teams with at
        least one Answer row, so a team with no answers yet must be checked
        against Team directly rather than assumed absent == unknown.
        """
        if Team.query.filter(Team.tid == tid).one_or_none() is None:
            raise UnknownTeamError(f"Unknown team {tid!r}")
        score = Controller.get_teams_score_by_tid().get(tid, 0)
        return (0, max(score, 0))

    @staticmethod
    def set_final_wager(tid, amount):
        _min, _max = Controller.get_final_wager_range(tid)
        if not (_min <= amount <= _max):
            raise GameProblem(f"Wager {amount} outside [{_min}, {_max}] for {tid}")
        wagers = Controller.get_final_wagers()
        wagers[tid] = amount
        Controller.set_state("final-wagers", json.dumps(wagers))
        return tid, amount

    @staticmethod
    def get_final_wagers():
        """{tid: amount} of wagers submitted so far this final question."""
        return json.loads(Controller.get_state("final-wagers") or "{}")

    @staticmethod
    def reveal_final_question():
        game = Game.query.one()
        if game.state != GameState.in_final:
            raise GameProblem("Final Jeopardy is not in progress")
        Controller.set_state("final", "revealed")
        return True

    @staticmethod
    def get_final_judged_teams():
        """tids already scored for this round's final question."""
        question = Controller.get_final_question()
        if question is None:
            return []
        return [a.team.tid for a in Answer.query.filter(Answer.question_id == question.id).all()]

    @staticmethod
    def answer_final(tid, correct):
        """Judge one team's Final Jeopardy answer using their stored wager."""
        game = Game.query.one()
        if game.state != GameState.in_final:
            raise GameProblem("Final Jeopardy is not in progress")
        question = Controller.get_final_question()
        if question is None:
            raise GameProblem("No final question configured for this round")
        wagers = Controller.get_final_wagers()
        if tid not in wagers:
            raise GameProblem(f"No wager submitted for {tid}")
        team = Team.query.filter(Team.tid == tid).one()

        # Replace any previous judgment for this team (host correcting a
        # misclick), same pattern as answer_dailydouble.
        Answer.query.filter(Answer.question_id == question.id, Answer.team_id == team.id).delete()

        response = Response.good if correct else Response.bad
        answer = Answer(response, team, question)
        answer.score_attributed = wagers[tid]
        db.session.add(answer)
        db.session.commit()
        return True

    @staticmethod
    def end_final() -> None:
        """Turn Final Jeopardy off. Use everywhere it ends (finish, next round)."""
        Controller.set_state("final", "")
        Controller.set_state("final-wagers", "{}")

    @staticmethod
    def cancel_final_round():
        """Back out of Final Jeopardy without ending the game -- e.g. started
        it by mistake, or resuming after a restart and want to bail. Any
        teams already judged keep their score; re-starting Final Jeopardy
        later lets the host re-judge them if needed."""
        game = Game.query.one()
        if game.state != GameState.in_final:
            raise GameProblem("Final Jeopardy is not in progress")
        game.state = GameState.in_round
        db.session.commit()
        Controller.end_final()
        return True

    @staticmethod
    def get_answer(column, row):
        app.logger.info("Answer requested for row: {} and col: {}".format(row, column))

        condition = and_(
            Question.row == row,
            Question.col == column,
            Question.round == Controller.get_current_round(),
        )
        _q = Question.query.filter(condition).one()
        _a = Answer.query.filter(Answer.question_id == _q.id).all()
        if len(_a) == 0:
            return {}
        answer = {}
        for a in _a:
            answer[a.team.tid] = a.response.value
        return answer

    @staticmethod
    def get_question_viewid_from_dbid(question_id):
        # Sorry for the ugly name but it says it all
        question = Question.query.get(question_id)
        qid = "c{}q{}".format(question.col, question.row)
        return qid

    @staticmethod
    def answer_normal(column, row, answers):
        app.logger.info("Answers submitted for question ({}, {}): {}".format(column, row, answers))
        # Answers looks like: ('team1', '-1'), ('team2', '1'), ('team3', '0')]

        condition = and_(
            Question.row == row,
            Question.col == column,
            Question.round == Controller.get_current_round(),
        )
        _q = Question.query.filter(condition).one()

        # Is there already an answer? If so update answers
        prev_answers = Answer.query.filter(Answer.question_id == _q.id).all()
        if prev_answers:
            for _answer in prev_answers:
                _answer.response = Response(int(answers[_answer.team.tid]))
                db.session.add(_answer)

        # Otherwise create new ones
        else:
            for tid, points in answers.items():
                team = Team.query.filter(Team.tid == tid).one()
                question = Question.query.get(_q.id)
                response = Response(int(points))
                db.session.add(Answer(response, team, question))

        db.session.commit()
        return True

    @staticmethod
    def answer_dailydouble(column, row, team, answer, waiger):
        app.logger.info(
            "Daily Double Answer submitted for question ({}, {}) by {}: {} waiger: {}.".format(
                column, row, team.tid, answer, waiger
            )
        )

        condition = and_(
            Question.row == row,
            Question.col == column,
            Question.round == Controller.get_current_round(),
        )
        _q = Question.query.filter(condition).one()

        # Delete existing answers
        Answer.query.filter(Answer.question_id == _q.id).delete()

        # Create a new one
        question = Question.query.get(_q.id)
        response = Response(int(answer))
        _answer = Answer(response, team, question)
        _answer.score_attributed = waiger
        db.session.add(_answer)

        db.session.commit()
        return True

    @staticmethod
    def _get_questions_status():
        """Full status about all questions on the current round's board"""
        questions = (
            db.session.query(Question.row, Question.col, Answer)
            .outerjoin(Answer)
            .filter(Question.round == Controller.get_current_round())
            .all()
        )
        return questions

    @staticmethod
    def get_questions_status_for_viewer():
        """Limited status view about all questions: answered or not"""
        questions = Controller._get_questions_status()

        results = {}
        for question in questions:
            _row, _col, _answer = question
            qid = "c{}q{}".format(_col, _row)
            results[qid] = _answer is not None

        return results

    @staticmethod
    def get_questions_status_for_host():
        """Status view about all questions
        Format looks like:
        {c1q3: {'team1': '-300' , 'team2': '500', ...}
        """
        questions = Controller._get_questions_status()

        results = {}
        for question in questions:
            _row, _col, _answer = question
            qid = "c{}q{}".format(_col, _row)
            # if new entry, add list
            if results.get(qid) is None:
                results[qid] = {}

            # skip empty answers
            if _answer is None:
                continue

            points = _answer.response.value * _answer.score_attributed
            tid = "team{}".format(_answer.team_id)
            results[qid][tid] = points

        return results

    @staticmethod
    def get_state(name):
        result = State.query.filter_by(name=name).one_or_none()
        if result is not None:
            return result.value
        else:
            return ""

    @staticmethod
    def get_complete_state():
        state = {}
        for s in State.query.all():
            state[s.name] = s.value
        return state

    @staticmethod
    def set_state(name, value):
        result = State.query.filter_by(name=name).one_or_none()
        if result is not None:
            if value is None:
                result.value = ""
            else:
                result.value = value
        else:
            db.session.add(State(name, value))
        db.session.commit()

    @staticmethod
    def db_backup_and_create_new():
        """
        Drop db connections, move file, create new db connection
        and re-init empty db
        """
        # TODO we might need to lock this thing to avoid state issues with viewers
        previous_roundfile = Game.query.one().round_filename
        _bkp_name = "ceopardy_{}_{}.db".format(
            datetime.now().strftime("%Y-%m-%d_%H%M"), previous_roundfile
        )
        # The live DB and its backups sit next to the user's data/ directory
        # (matches SQLALCHEMY_DATABASE_URI in ceopardy/__init__.py).
        db_path = os.path.join(config["BASE_DIR"], config["DATABASE_FILENAME"])
        bkp_path = os.path.join(config["BASE_DIR"], _bkp_name)
        app.logger.info("Backing up current game to {}".format(bkp_path))
        db.session.remove()
        db.engine.dispose()
        if os.path.exists(db_path):
            os.rename(db_path, bkp_path)
        else:
            app.logger.warning("Expected DB file at %s was missing; skipping rename", db_path)
        db.create_all()
        Controller._init()
        app.logger.info("SQL Engine reconnected, empty database recreated. We are ready to go!")
