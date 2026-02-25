#!/usr/bin/env python3
"""Generate Spanish translations and explanations for all questions using Gemini API."""
import json, os, sys, time, urllib.request

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
DATA = "data/questions.json"
BATCH_SIZE = 5  # questions per API call


def call_gemini(prompt: str, retries=3) -> str:
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}",
        data=body, headers={"Content-Type": "application/json"}
    )
    for attempt in range(retries):
        try:
            resp = urllib.request.urlopen(req, timeout=90)
            result = json.loads(resp.read())
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"  Retry {attempt+1}: {e}", flush=True)
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
    return ""


def parse_json_response(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except:
        # Try to find JSON array in response
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except:
                pass
    return []


def build_prompt(batch: list) -> str:
    questions_text = ""
    for q in batch:
        # Truncate long options for LV3
        opts_str = ", ".join(o[:60] for o in q.get("options", [])[:5])
        questions_text += f"""
---
ID: {q['id']}
Section: {q['section']} Teil {q['teil']}
Question: {q.get('question', '')}
Options: {opts_str}
Correct: {q.get('correct', '')}
"""

    return f"""You are a German B1 exam tutor helping a Spanish speaker prepare for the telc B1 exam.

For each question below, provide:
1. `question_es`: Spanish translation of the German question
2. `explanation_es`: Brief explanation in Spanish of WHY the correct answer is correct (2-3 sentences max)
3. `vocabulary`: Array of 3-5 key German words from the question with Spanish translations

Return ONLY a JSON array like:
[
  {{
    "id": "question-id",
    "question_es": "Spanish translation...",
    "explanation_es": "Explanation...",
    "vocabulary": [{{"de": "German", "es": "Spanish"}}, ...]
  }},
  ...
]

Questions:
{questions_text}

Return ONLY valid JSON array, no markdown."""


def main():
    with open(DATA) as f:
        questions = json.load(f)

    # Find questions needing translations
    needs_translation = [q for q in questions if not q.get("question_es")]
    print(f"Total questions: {len(questions)}", flush=True)
    print(f"Needing translation: {len(needs_translation)}", flush=True)

    # Process in batches
    translated = 0
    failed = 0
    for i in range(0, len(needs_translation), BATCH_SIZE):
        batch = needs_translation[i:i+BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(needs_translation) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"Batch {batch_num}/{total_batches} ({len(batch)} questions)...", flush=True)

        prompt = build_prompt(batch)
        response = call_gemini(prompt)
        if not response:
            print(f"  FAILED - empty response", flush=True)
            failed += len(batch)
            continue

        results = parse_json_response(response)
        if not results:
            print(f"  FAILED - couldn't parse JSON", flush=True)
            failed += len(batch)
            continue

        # Map results by ID
        results_map = {r["id"]: r for r in results if "id" in r}

        for q in batch:
            if q["id"] in results_map:
                r = results_map[q["id"]]
                # Find the question in the main list and update
                for j, orig in enumerate(questions):
                    if orig["id"] == q["id"]:
                        questions[j]["question_es"] = r.get("question_es", "")
                        questions[j]["explanation_es"] = r.get("explanation_es", questions[j].get("explanation_es", ""))
                        questions[j]["vocabulary"] = r.get("vocabulary", questions[j].get("vocabulary", []))
                        translated += 1
                        break
            else:
                failed += 1

        print(f"  → {len(results_map)}/{len(batch)} translated", flush=True)

        # Save periodically
        if batch_num % 10 == 0:
            with open(DATA, "w") as f:
                json.dump(questions, f, ensure_ascii=False, indent=2)
            print(f"  [checkpoint saved]", flush=True)

        time.sleep(0.5)  # Rate limit

    # Final save
    with open(DATA, "w") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    print(f"\nDone! Translated: {translated}, Failed: {failed}", flush=True)
    has_es = sum(1 for q in questions if q.get("question_es"))
    print(f"Questions with Spanish translation: {has_es}/{len(questions)}", flush=True)


if __name__ == "__main__":
    main()
