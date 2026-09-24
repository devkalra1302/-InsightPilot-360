"""
ai/explainer.py
Phase 2 — Step 7: AI Explanation Layer.

Job of this module (and ONLY this module):
- Take KPI numbers that domains/*.py has ALREADY CALCULATED and ask
  Claude to write a short (1-2 sentence) plain-English narration of them.
  Example: {"revenue": 251320.24, "growth_pct": 62.09} might become
  "Revenue grew 62% this period, a strong result worth investigating
  further."

NOT this module's job, EVER:
- Calculating anything. This file only ever sends numbers OUT to Claude
  and gets a SENTENCE back. It never sends raw data, and the numbers it
  sends are never modified by the AI's response — the AI cannot change
  what your dashboard displays as fact, only add a sentence describing
  facts you already computed. This is the spec's "Evidence-Grounded AI
  Explanation" requirement (Section 5): the AI narrates, it never invents
  or calculates a KPI.

SAME "DON'T CRASH THE DASHBOARD" DISCIPLINE AS EVERY OTHER PHASE 2 FILE:
- No API key configured, an invalid key, no internet, or any other
  failure -> this returns a plain fallback message instead of raising an
  exception. app.py can call this without a try/except of its own and
  the dashboard keeps working normally, just without the AI sentence.
"""

import os
from dotenv import load_dotenv

# Loads the .env file in the project root into environment variables.
# If .env doesn't exist or has no key, this simply does nothing — it
# does NOT raise an error, which is exactly the "fail gracefully"
# behavior we want here.
load_dotenv()

# Cheapest current Claude model — plenty capable for a one-sentence
# narration job, and keeps this feature's running cost close to zero.
MODEL_NAME = "claude-haiku-4-5-20251001"

UNAVAILABLE_MESSAGE = "AI explanation unavailable (no API key configured or request failed)."


def _build_prompt(domain: str, kpis: dict) -> str:
    """
    Turns the KPI dict into a short, plain-text prompt. Only sends
    KPI names and their already-calculated values — never the raw
    DataFrame, never anything the AI could mistake for permission to
    calculate its own numbers.
    Skips any KPI that's a list (Top Products, Reorder Flag, etc.) or a
    NOT_AVAILABLE string, since those aren't single figures to narrate.
    """
    lines = []
    for key, value in kpis.items():
        if isinstance(value, str):
            continue  # NOT_AVAILABLE message — nothing to narrate
        if isinstance(value, list):
            continue  # list-shaped KPI — narrating a list isn't this file's job
        lines.append(f"- {key}: {value}")

    numbers_block = "\n".join(lines) if lines else "(no numeric KPIs available)"

    return (
        f"You are writing a one-sentence summary for a business dashboard's "
        f"{domain} section. Here are the already-calculated numbers:\n\n"
        f"{numbers_block}\n\n"
        f"Write exactly 1-2 short, plain-English sentences highlighting the "
        f"most notable thing here. Do not invent any numbers beyond what is "
        f"given above. Do not use markdown formatting."
    )


def generate_explanation(domain: str, kpis: dict) -> str:
    """
    The one function app.py calls. Returns a short narration string, or
    the fallback message if anything goes wrong. Every failure path is
    caught here so app.py never needs to worry about this call crashing
    the dashboard.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return UNAVAILABLE_MESSAGE

    try:
        # Imported here (not at the top of the file) so that if the
        # `anthropic` package somehow isn't installed, only this function
        # fails gracefully — it doesn't prevent the whole app.py from
        # starting up.
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        prompt = _build_prompt(domain, kpis)

        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    except Exception:
        # Any failure — bad key, no internet, rate limit, unexpected
        # response shape — falls back to the same safe message. We
        # deliberately don't print the raw error to the dashboard (it
        # could leak technical details to an end user); it's swallowed
        # here rather than propagated.
        return UNAVAILABLE_MESSAGE


if __name__ == "__main__":
    # Standalone test: run `python ai/explainer.py` from the repo root.
    # Uses a small hand-built KPI dict (not a real domain file) since
    # this module's only job is turning numbers into a sentence — it
    # doesn't need a CSV to test that.
    sample_kpis = {
        "revenue": 251320.24,
        "profit": 77461.17,
        "margin_pct": 30.82,
        "growth_pct": 62.09,
    }
    print("Testing ai/explainer.py with sample Sales KPIs...")
    print(f"API key found: {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
    print()
    result = generate_explanation("Sales", sample_kpis)
    print("Result:", result) 