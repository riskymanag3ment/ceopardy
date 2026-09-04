# Ceopardy
# https://github.com/obilodeau/ceopardy/
#
# Olivier Bilodeau <olivier@bottomlesspit.org>
# Copyright (C) 2017, 2018, 2019, 2025, 2026 Olivier Bilodeau
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
import csv
import glob
import html
import io
import os
import re

from ceopardy.config import config
from ceopardy.exceptions import GamefileParsingError, InvalidQuestionId, QuestionParsingError


def parse_questions(filename):
    """Parses a question file.
    Returns a dict (of categories) of lists of questions (in score order)
    """
    # TODO should drop the old format entirely?
    # if so use html and integrate answers into question file
    # people can then use asciidoctor or markdown to render questions from
    # a simpler format
    questions = {}
    cur_category = None
    try:
        with open(filename, "r") as f:
            for line in f:
                line = line.rstrip("\r\n")

                # skip comments or whitespace lines
                if re.match(r"^\s*(#|$)", line):
                    continue

                # it's a category
                m = re.match(r"^>(.*)$", line)
                if m:
                    # create category entry
                    questions[m.group(1)] = list()
                    cur_category = m.group(1)
                    continue

                # convert fake new-lines into real ones
                line = re.sub(r"\\n", "\n", line)

                # it's a question
                questions[cur_category].append(line)

    except Exception as e:
        context = "Problem parsing the question file: {}".format(filename)
        raise QuestionParsingError(context) from e

    return questions


def parse_gamefile(filename):
    """Parses a game file. A game file holds the categories that are going to be
     played in order.
    Returns a list of category strings and a final question dict
    """
    # TODO should drop the old format entirely?
    # if so we need to be able to express final question somehow
    categories = list()
    final = None
    try:
        with open(filename, "r") as f:
            for line in f:
                line = line.rstrip("\r\n")

                # match: final: [category] text
                m = re.match(r"final: \[([^]]+)\] (.*)$", line)
                if m:
                    final = {"category": m.group(1), "question": m.group(2)}
                    continue

                categories.append(line)

    except Exception as e:
        context = "Problem parsing the game file: {}".format(filename)
        raise GamefileParsingError(context) from e

    return categories, final


def question_to_html(question_text):
    """Parses the questions from the Beopardy Game Board format"""
    question_text = html.escape(question_text)

    # Warning, we don't support nested line heading options
    # UTF-8 is just killed since everything is UTF-8 now
    if question_text.startswith("[utf8]"):
        question_text = question_text.lstrip("[utf8]")

    # Fixed width strings
    if question_text.startswith("[fixed]"):
        question_text = question_text.lstrip("[fixed]")
        question_text = "<tt>{}</tt>".format(question_text)

    # Parsing images
    m = re.search(r"^\[img:([^\]]*)\]$", question_text)
    if m:
        # TODO file names will have to be hard to guess if we go multi-client
        # TODO push style into CSS
        img_tmpl = (
            '<img src="/static/game-media/{}" width="100%"'
            ' style="max-height: 100%; max-width: 100%; object-fit: contain;">'
        )
        return img_tmpl.format(m.group(1))

    # Parsing videos
    m = re.search(r"^\[video:([^\]]*)\]$", question_text)
    if m:
        # TODO file names will have to be hard to guess if we go multi-client
        # TODO push style into CSS
        return """
            <video src="/static/game-media/{}"
                autoplay
                controls
                style="max-height: 100%; max-width: 100%; object-fit: contain;">
            </video>
        """.format(m.group(1))

    # Transform new lines into <br>
    question_text = re.sub(r"\n", "<br/>", question_text)

    return "<p>" + question_text + "</p>"


def parse_questions_csv(file_stream):
    """Parse a spreadsheet-style CSV covering one or more rounds, plus an
    optional Final Jeopardy row.

    Expected shape (the header row is cosmetic and ignored). Each point
    value gets its own clue column immediately followed by its own answer
    column -- the answer column may be left blank if that clue shouldn't
    have a revealable correct question:
        round, category,    100,        100 answer, 200,        200 answer, ...
        1,     Category A,  question 1, answer 1,    question 2, ,          ...
        1,     Category B,  ...
        2,     Category C,  ...
        final, Final Cat.,  Final question text, Final answer

    Rows sharing the same "round" value must be grouped together (in the
    order they should be played) and each round needs exactly
    CATEGORIES_PER_GAME rows of QUESTIONS_PER_CATEGORY clue/answer pairs.
    Prefix a clue cell with "[dbl]" to mark it a Daily Double (same
    convention as the plain-text question format). At most one "final" row
    is allowed (case-insensitive in the round column), attached to
    whichever round is played last.

    Internally, a clue and its answer are recombined into this module's
    plain-text "<clue> :: <answer>" convention (see parse_questions() /
    controller.setup_questions()) so the rest of the pipeline -- the
    generated Questions-<slug>.cp file, the game engine -- needs no
    separate code path for CSV-sourced content.

    Returns (rounds, final):
      rounds: [{category_name: [q1, q2, ...]}, ...], one dict per round in
              the order rounds first appear in the sheet.
      final: {"category": ..., "question": ...} or None.
    """
    text = io.TextIOWrapper(file_stream, encoding="utf-8-sig")
    rows = [row for row in csv.reader(text) if any(cell.strip() for cell in row)]
    if not rows:
        raise QuestionParsingError("The CSV file is empty")

    data_rows = rows[1:]  # first row is a header, purely for the author's benefit
    nb_questions = config["QUESTIONS_PER_CATEGORY"]
    expected_cols = 2 + 2 * nb_questions  # round, category, then (clue, answer) x N

    def _combine(clue, answer):
        return f"{clue} :: {answer}" if answer else clue

    round_order = []
    rounds = {}
    seen_categories = set()
    final = None

    for i, raw_row in enumerate(data_rows, start=2):  # +2: 1-indexed, header consumed
        row = [c.strip() for c in raw_row]

        if row[0].lower() == "final":
            if final is not None:
                raise QuestionParsingError(f"Row {i}: only one 'final' row is allowed")
            category = row[1] if len(row) > 1 else ""
            clue = row[2] if len(row) > 2 else ""
            answer = row[3] if len(row) > 3 else ""
            if not category or not clue:
                raise QuestionParsingError(
                    f"Row {i}: a 'final' row needs a category and a clue "
                    "(round, category, clue, answer)"
                )
            final = {"category": category, "question": _combine(clue, answer)}
            continue

        if len(row) != expected_cols:
            raise QuestionParsingError(
                f"Row {i}: expected {expected_cols} columns (round, category, then "
                f"a clue + answer column for each of the {nb_questions} questions), "
                f"got {len(row)}"
            )
        round_label, category = row[0], row[1]
        if not round_label:
            raise QuestionParsingError(f"Row {i}: missing round number")
        if not category:
            raise QuestionParsingError(f"Row {i}: missing category name")
        if category in seen_categories:
            raise QuestionParsingError(
                f"Row {i}: duplicate category '{category}' (category names must be "
                "unique across the whole sheet, even across different rounds)"
            )

        pairs = row[2:]
        questions = []
        for q_idx in range(nb_questions):
            clue = pairs[2 * q_idx]
            answer = pairs[2 * q_idx + 1]
            if not clue:
                raise QuestionParsingError(
                    f"Row {i} ({category}): question {q_idx + 1}'s clue is empty"
                )
            questions.append(_combine(clue, answer))

        if round_label not in rounds:
            round_order.append(round_label)
            rounds[round_label] = {}
        seen_categories.add(category)
        rounds[round_label][category] = questions

    expected_categories = config["CATEGORIES_PER_GAME"]
    for label in round_order:
        count = len(rounds[label])
        if count != expected_categories:
            raise QuestionParsingError(
                f"Round '{label}': expected {expected_categories} categories, found {count}"
            )

    return [rounds[label] for label in round_order], final


def write_questions_cp(base_dir, filename, categories):
    """Serialize {category: [q1, q2, ...]} to the plain-text question format."""
    path = os.path.join(base_dir, "data", filename)
    with open(path, "w") as f:
        for category, questions in categories.items():
            f.write(">{}\n".format(category))
            for q in questions:
                # Preserve literal newlines using the existing "\n" escape.
                f.write("{}\n".format(q.replace("\n", "\\n")))
            f.write("\n")


def write_roundfile(base_dir, filename, category_names, final):
    """Serialize a round's category order (+ optional final) to a .round file."""
    path = os.path.join(base_dir, "data", filename)
    with open(path, "w") as f:
        for name in category_names:
            f.write("{}\n".format(name))
        if final is not None:
            f.write("final: [{}] {}\n".format(final["category"], final["question"]))


def list_roundfiles():
    """List available roundfiles in config's data directory"""

    _glob = config["BASE_DIR"] + "data/*.round"
    # return file names only
    return [os.path.basename(_f) for _f in glob.glob(_glob)]


def parse_question_id(qid):
    """
    Parses a question id in the form category X question Y (cXqY) and
    returns a tuple with category, question or None if it didn't work.
    """
    match = re.match("c([0-9]+)q([0-9]+)", qid)
    if match is None:
        raise InvalidQuestionId("Invalid Question Id: {}".format(qid))
    col, row = match.groups()
    return (col, row)


def filter_answer_form(data, dailydouble=False):
    answers = {}
    for key, value in data.items():
        if dailydouble is False:
            if not key.endswith("-dailydouble"):
                answers[key] = value
        else:
            if key.endswith("-dailydouble"):
                key = key.rstrip("-dailydouble")
                answers[key] = value
    return answers
