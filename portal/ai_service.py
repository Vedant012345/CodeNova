"""
CodeNova AI Service — Groq Integration v3
Bulletproof quiz generation with exhaustive JSON recovery strategies.
"""
import os
import json
import re
import logging
import time
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

try:
    from groq import Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",   # Most capable — best JSON output
    "llama-3.1-8b-instant",      # Fast fallback
    "llama3-70b-8192",           # Legacy fallback
    "gemma2-9b-it",              # Last resort
]
TIMEOUT = 45


def _get_client():
    if not _GROQ_AVAILABLE:
        logger.warning("groq package not installed.")
        return None
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set.")
        return None
    return Groq(api_key=GROQ_API_KEY)


def _call_with_fallback(messages_payload, max_tokens=3000, temperature=0.1):
    """Try each model in order. Returns (response_text, model_used)."""
    client = _get_client()
    if not client:
        raise RuntimeError("Groq client unavailable — check GROQ_API_KEY")

    last_error = None
    for model in FALLBACK_MODELS:
        try:
            logger.debug("Trying model: %s", model)
            resp = client.chat.completions.create(
                model=model,
                messages=messages_payload,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=TIMEOUT,
            )
            text = resp.choices[0].message.content.strip()
            logger.info("Model %s succeeded. Response[:150]: %s", model, text[:150])
            return text, model
        except Exception as e:
            logger.warning("Model %s failed: %s", model, e)
            last_error = e
            time.sleep(0.3)
    raise last_error


# ─── JSON Extraction ──────────────────────────────────────────────────────────

def _strip_markdown(raw: str) -> str:
    """Remove markdown fences and normalise quotes."""
    raw = re.sub(r"```(?:json)?\s*", "", raw)
    raw = re.sub(r"```", "", raw)
    # Smart quotes → straight quotes
    raw = raw.replace("\u201c", '"').replace("\u201d", '"')
    raw = raw.replace("\u2018", "'").replace("\u2019", "'")
    return raw.strip()


def _extract_outermost(raw: str, open_ch: str, close_ch: str) -> str:
    """Extract the first complete balanced block of open_ch...close_ch."""
    depth = 0
    start = None
    for i, ch in enumerate(raw):
        if ch == open_ch:
            if depth == 0:
                start = i
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0 and start is not None:
                return raw[start:i + 1]
    return ""


def _fix_trailing_commas(s: str) -> str:
    return re.sub(r",\s*([\]}])", r"\1", s)


def _try_parse(s: str):
    """Try json.loads with trailing-comma fix. Returns dict/list or None."""
    for candidate in (s, _fix_trailing_commas(s)):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _extract_json(raw: str):
    """
    Multi-strategy JSON extractor. Returns parsed object or None.
    Strategies (in order):
      1. Direct parse after markdown strip
      2. Extract outermost { } block
      3. Extract outermost [ ] block (flat array response)
      4. Scan every { } blob for a question-like object
    """
    raw = _strip_markdown(raw)

    # Strategy 1: direct
    result = _try_parse(raw)
    if result is not None:
        return result

    # Strategy 2: outermost object
    obj_str = _extract_outermost(raw, "{", "}")
    if obj_str:
        result = _try_parse(obj_str)
        if result is not None:
            return result

    # Strategy 3: flat array
    arr_str = _extract_outermost(raw, "[", "]")
    if arr_str:
        result = _try_parse(arr_str)
        if isinstance(result, list):
            return {"questions": result}

    # Strategy 4: collect every { } blob
    blobs = re.findall(r'\{[^{}]*\}', raw, re.DOTALL)
    collected = []
    for blob in blobs:
        parsed = _try_parse(blob)
        if isinstance(parsed, dict) and ("text" in parsed or "question" in parsed):
            collected.append(parsed)
    if collected:
        return {"questions": collected}

    return None


# ─── Question Normalisation ───────────────────────────────────────────────────

def _get_field(d: dict, *keys, default=""):
    """Return first non-empty value from candidate keys (case-insensitive)."""
    d_lower = {k.lower(): v for k, v in d.items()}
    for key in keys:
        val = d_lower.get(key.lower(), "")
        if val and str(val).strip():
            return str(val).strip()
    return default


def _resolve_correct_letter(correct_raw: str, options: dict) -> str:
    """
    Turn ANY correct-answer format into a single letter A/B/C/D.
    Handles: "A", "A.", "A)", "(A)", "B. Paris", "Paris" (matched to option text).
    """
    if not correct_raw:
        return ""

    c = correct_raw.strip()

    # Already a single letter
    if c.upper() in ("A", "B", "C", "D"):
        return c.upper()

    # Starts with letter + punctuation: "A.", "A)", "A:"
    m = re.match(r'^([A-Da-d])[.):\s]', c)
    if m:
        return m.group(1).upper()

    # Number → letter mapping: "1"→A, "2"→B, "3"→C, "4"→D
    if c in ("1", "2", "3", "4"):
        return "ABCD"[int(c) - 1]

    # Full word answer — match against option text
    c_lower = c.lower()
    for letter, text in options.items():
        if text.lower() == c_lower or c_lower in text.lower():
            return letter

    # Last chance: find any A-D letter in the string
    m2 = re.search(r'\b([A-Da-d])\b', c)
    if m2:
        return m2.group(1).upper()

    return ""


def _normalise_options(q: dict) -> dict:
    """
    Extract A/B/C/D options from any format:
      - option_a / option_b / ...
      - a / b / c / d
      - choices: {"A": ..., "B": ..., ...}
      - options: ["...", "...", "...", "..."]  (list)
      - numbered: "1", "2", "3", "4"
    Returns {"A": text, "B": text, "C": text, "D": text} or empty dict.
    """
    q_lower = {k.lower(): v for k, v in q.items()}

    # Format 1: option_a / option_b / option_c / option_d
    if all(f"option_{l}" in q_lower for l in ("a", "b", "c", "d")):
        return {
            "A": str(q_lower["option_a"]).strip(),
            "B": str(q_lower["option_b"]).strip(),
            "C": str(q_lower["option_c"]).strip(),
            "D": str(q_lower["option_d"]).strip(),
        }

    # Format 2: single letters a / b / c / d
    if all(l in q_lower for l in ("a", "b", "c", "d")):
        return {
            "A": str(q_lower["a"]).strip(),
            "B": str(q_lower["b"]).strip(),
            "C": str(q_lower["c"]).strip(),
            "D": str(q_lower["d"]).strip(),
        }

    # Format 3: numbered 1 / 2 / 3 / 4
    if all(str(n) in q_lower for n in (1, 2, 3, 4)):
        return {
            "A": str(q_lower["1"]).strip(),
            "B": str(q_lower["2"]).strip(),
            "C": str(q_lower["3"]).strip(),
            "D": str(q_lower["4"]).strip(),
        }

    # Format 4: choices dict {"A": ..., "B": ..., ...}
    choices = q_lower.get("choices") or q_lower.get("options")
    if isinstance(choices, dict):
        norm = {k.upper(): str(v).strip() for k, v in choices.items()}
        if all(l in norm for l in ("A", "B", "C", "D")):
            return {l: norm[l] for l in "ABCD"}

    # Format 5: options list ["opt1", "opt2", "opt3", "opt4"]
    if isinstance(choices, list) and len(choices) >= 4:
        return {
            "A": str(choices[0]).strip(),
            "B": str(choices[1]).strip(),
            "C": str(choices[2]).strip(),
            "D": str(choices[3]).strip(),
        }

    return {}


def _validate_questions(questions_raw: list) -> list:
    """Normalise and validate a list of raw question dicts."""
    validated = []
    for i, q in enumerate(questions_raw):
        if not isinstance(q, dict):
            continue

        text = _get_field(q, "text", "question", "question_text", "q")
        if not text:
            logger.warning("Q%d: missing question text — skipping", i + 1)
            continue

        options = _normalise_options(q)
        if not options:
            logger.warning("Q%d: could not extract A/B/C/D options — skipping", i + 1)
            continue

        correct_raw = _get_field(q, "correct", "answer", "correct_answer", "ans")
        correct = _resolve_correct_letter(correct_raw, options)
        if not correct:
            logger.warning("Q%d: could not resolve correct answer from %r — skipping", i + 1, correct_raw)
            continue

        explanation = _get_field(q, "explanation", "reason", "rationale", "hint")

        validated.append({
            "text":        text,
            "option_a":    options["A"],
            "option_b":    options["B"],
            "option_c":    options["C"],
            "option_d":    options["D"],
            "correct":     correct,
            "explanation": explanation,
            "order":       i + 1,
        })

    return validated


def _extract_questions_from_parsed(data) -> list:
    """
    Navigate any JSON structure to find the list of question objects.
    Handles: {"questions": [...]}, {"quiz": {"questions": [...]}}, [...]
    """
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    # Direct key
    for key in ("questions", "quiz_questions", "items", "data", "results"):
        val = data.get(key)
        if isinstance(val, list):
            return val
        # One level deep
        if isinstance(val, dict):
            for inner_key in ("questions", "items"):
                inner = val.get(inner_key)
                if isinstance(inner, list):
                    return inner

    # Nested quiz wrapper
    for key in ("quiz", "content", "output", "response"):
        val = data.get(key)
        if isinstance(val, dict):
            for inner_key in ("questions", "items"):
                inner = val.get(inner_key)
                if isinstance(inner, list):
                    return inner

    # Last resort: any list value in the dict
    for val in data.values():
        if isinstance(val, list) and len(val) > 0:
            return val

    return []


# ─── Prompt ───────────────────────────────────────────────────────────────────

QUIZ_SYSTEM_PROMPT = """\
You are a JSON API. You output ONLY raw JSON — nothing else.

Generate {n} multiple-choice quiz questions about the given topic.

Respond with ONLY this JSON structure (no markdown, no extra text):
{{"questions":[{{"text":"Question?","option_a":"...","option_b":"...","option_c":"...","option_d":"...","correct":"A","explanation":"..."}}]}}

Rules:
- "correct" must be exactly one uppercase letter: A, B, C, or D
- All four options must be distinct and non-trivial  
- No markdown, no backticks, no preamble, no explanation outside JSON
- Output must start with {{ and end with }}
"""


# ─── Public API ───────────────────────────────────────────────────────────────

def generate_quiz_questions(topic: str, subject: str = "", n: int = 5) -> dict:
    """
    Generate n quiz questions via Groq.
    Returns {"success": True, "questions": [...], "model_used": "..."}
         or {"success": False, "error": "...", "questions": []}
    """
    if not _GROQ_AVAILABLE or not GROQ_API_KEY:
        return {
            "success": False,
            "error": "AI service not configured. Add GROQ_API_KEY to your environment.",
            "questions": [],
        }

    context_line = f"Topic: {topic}" + (f"\nSubject: {subject}" if subject else "")

    messages = [
        {"role": "system", "content": QUIZ_SYSTEM_PROMPT.format(n=n)},
        {
            "role": "user",
            "content": (
                f"{context_line}\n\n"
                f"Generate exactly {n} questions. "
                f"Output ONLY the JSON object starting with {{ and ending with }}."
            ),
        },
    ]

    raw = ""
    model_used = "unknown"

    try:
        raw, model_used = _call_with_fallback(messages, max_tokens=3000, temperature=0.1)

        # Extract and parse JSON
        parsed = _extract_json(raw)
        if parsed is None:
            logger.error("All JSON extraction strategies failed. Raw[:500]:\n%s", raw[:500])
            return {
                "success": False,
                "error": "AI response could not be parsed. Please try again.",
                "questions": [],
            }

        # Navigate to questions list
        questions_raw = _extract_questions_from_parsed(parsed)
        if not questions_raw:
            logger.error("No questions list found in parsed data: %s", str(parsed)[:300])
            return {
                "success": False,
                "error": "AI returned an empty quiz. Please try again.",
                "questions": [],
            }

        # Validate and normalise
        validated = _validate_questions(questions_raw)

        if not validated:
            logger.error(
                "Validation rejected all %d questions. Sample: %s",
                len(questions_raw), str(questions_raw[:1])[:300]
            )
            return {
                "success": False,
                "error": (
                    f"AI returned {len(questions_raw)} question(s) but none passed validation. "
                    "Please try again — this is usually a one-off issue."
                ),
                "questions": [],
            }

        return {"success": True, "questions": validated, "model_used": model_used}

    except json.JSONDecodeError as e:
        logger.error("JSONDecodeError: %s | Raw[:400]: %s", e, raw[:400])
        return {
            "success": False,
            "error": "AI response could not be parsed. Please try again.",
            "questions": [],
        }
    except Exception as e:
        logger.error("Groq error: %s", e)
        err = str(e).lower()
        if "rate_limit" in err or "429" in err:
            msg = "Rate limit reached. Please wait 30 seconds and try again."
        elif "timeout" in err:
            msg = "Request timed out. Try fewer questions."
        elif "model_not_found" in err or "does not exist" in err:
            msg = "AI model unavailable. Please try again shortly."
        else:
            msg = f"AI service error: {str(e)[:150]}"
        return {"success": False, "error": msg, "questions": []}


# ─── Chatbot ──────────────────────────────────────────────────────────────────

CHAT_SYSTEM_PROMPT = """\
You are NovaBot — a friendly, expert coding and academic tutor for CodeNova.
Help students understand concepts, debug code, and learn effectively.
- Be concise but thorough.
- Use code blocks for code examples.
- Break down complex concepts step by step.
- Current topic: {topic}
"""


def chat_with_student(user_message: str, history: list, topic: str = "") -> dict:
    if not _GROQ_AVAILABLE or not GROQ_API_KEY:
        return {"success": False, "error": "AI chatbot not configured. Add GROQ_API_KEY."}

    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT.format(
            topic=topic or "general academics and coding"
        )}
    ]
    for msg in history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    try:
        reply, model_used = _call_with_fallback(messages, max_tokens=1024, temperature=0.6)
        return {"success": True, "reply": reply, "model_used": model_used}
    except Exception as e:
        logger.error("Chatbot error: %s", e)
        err = str(e).lower()
        if "rate_limit" in err or "429" in err:
            msg = "I'm busy right now — please try again in 30 seconds."
        else:
            msg = "Having trouble connecting. Please try again in a moment."
        return {"success": False, "error": msg}
