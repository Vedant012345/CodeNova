"""
CodeNova Quiz Parser — v2
Converts plain-text quiz format into structured Question data.

Supported formats:

Multi-line (preferred):
    Q1: What is Python?
    A. A snake
    B. A programming language
    C. An operating system
    D. A database
    Answer: B

Compact single-line:
    Q1: What is 2+2? A. 3 B. 4 C. 5 D. 6 Answer: B
"""
import re
import logging

logger = logging.getLogger(__name__)


class QuizParseError(Exception):
    pass


def _extract_options_and_answer(lines_str: str):
    """
    Given the text after the question line, extract A/B/C/D and Answer.
    Returns (options_dict, answer_letter) or raises QuizParseError.
    """
    options = {}
    answer  = None

    # Try multi-line approach first
    for line in lines_str.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Option: A. text  or  A) text  or  A: text  or  (A) text
        opt_m = re.match(r"^\(?([A-Da-d])\)?[.):]\s+(.+)", line)
        if opt_m:
            options[opt_m.group(1).upper()] = opt_m.group(2).strip()
            continue
        # Answer line
        ans_m = re.match(r"(?:Answer|Ans|Correct)\s*[.:\-]?\s*([A-Da-d])\b", line, re.IGNORECASE)
        if ans_m:
            answer = ans_m.group(1).upper()

    if len(options) == 4 and answer:
        return options, answer

    # Fallback: compact single-line scan
    # Find all  "A. text"  "B. text" etc. followed eventually by Answer: X
    compact_opts = re.findall(r"([A-Da-d])[.)]\s*((?:(?![A-Da-d][.)]).)+)", lines_str, re.IGNORECASE)
    compact_ans  = re.search(r"(?:Answer|Ans(?:wer)?)\s*[.:\-]?\s*([A-Da-d])\b", lines_str, re.IGNORECASE)

    if len(compact_opts) >= 4 and compact_ans:
        opts = {k.upper(): v.strip() for k, v in compact_opts[:4]}
        if set(opts.keys()) == {"A", "B", "C", "D"}:
            return opts, compact_ans.group(1).upper()

    # Diagnose what's missing
    missing = [k for k in ("A", "B", "C", "D") if k not in options]
    if missing:
        raise QuizParseError(
            f"Missing options: {', '.join(missing)}. "
            "Each question needs options A, B, C and D."
        )
    if answer is None:
        raise QuizParseError("Missing answer line. Add: Answer: A (or B/C/D)")

    raise QuizParseError("Could not parse options and answer from this block.")


def _parse_block(block: str, order: int) -> dict:
    """Parse a single question block into a structured dict."""
    lines = block.strip().split("\n")
    if not lines:
        raise QuizParseError("Empty block.")

    # Extract question text — strip Q<n>: prefix
    q_line = lines[0].strip()
    q_text = re.sub(r"^Q\s*\d+\s*[:.)\-]\s*", "", q_line, flags=re.IGNORECASE).strip()
    if not q_text:
        raise QuizParseError("Question text is empty.")

    remainder = "\n".join(lines[1:])

    # For compact single-line questions, the question text may contain
    # the options embedded after it — detect if remainder is empty
    if not remainder.strip():
        # All on one line — split on first option marker
        m = re.search(r"\s+[A-Da-d][.)]\s", q_line)
        if m:
            q_text    = q_line[:m.start()].strip()
            q_text    = re.sub(r"^Q\s*\d+\s*[:.)\-]\s*", "", q_text, flags=re.IGNORECASE).strip()
            remainder = q_line[m.start():]

    options, answer = _extract_options_and_answer(remainder)

    return {
        "text":     q_text,
        "option_a": options["A"],
        "option_b": options["B"],
        "option_c": options["C"],
        "option_d": options["D"],
        "correct":  answer,
        "order":    order,
    }


def parse_quiz_text(raw_text: str) -> list:
    """
    Parse plain-text quiz into a list of question dicts.
    Raises QuizParseError if no valid questions found.
    """
    if not raw_text or not raw_text.strip():
        raise QuizParseError("Quiz text is empty. Please enter at least one question.")

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Split into blocks on Q<n> markers
    blocks = re.split(r"(?=^Q\s*\d+\s*[:.)\-])", text, flags=re.MULTILINE | re.IGNORECASE)
    blocks = [b.strip() for b in blocks if b.strip()]

    # Fallback: split on double newlines
    if not blocks or (len(blocks) == 1 and not re.match(r"^Q\s*\d+", blocks[0], re.IGNORECASE)):
        blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]

    if not blocks:
        raise QuizParseError("No question blocks found. Use Q1:, Q2: etc. to mark questions.")

    questions = []
    errors    = []

    for idx, block in enumerate(blocks, 1):
        try:
            questions.append(_parse_block(block, idx))
        except QuizParseError as e:
            errors.append(f"Q{idx}: {e}")

    if not questions:
        raise QuizParseError("No valid questions found.\n" + "\n".join(errors))

    if errors:
        logger.warning("Quiz parse warnings: %s", errors)

    return questions


def validate_and_preview(raw_text: str) -> dict:
    """Validate without saving. Returns success/error dict."""
    try:
        questions = parse_quiz_text(raw_text)
        return {"success": True, "questions": questions, "count": len(questions)}
    except QuizParseError as e:
        return {"success": False, "error": str(e)}
