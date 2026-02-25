#!/usr/bin/env python3
"""Fast translation - larger batches, parallel requests."""
import json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
DATA = "data/questions.json"
BATCH_SIZE = 20
WORKERS = 4


def call_gemini(prompt):
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}",
        data=body, headers={"Content-Type": "application/json"}
    )
    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
            return json.loads(text)
        except Exception as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    return []


def build_prompt(batch):
    items = ""
    for q in batch:
        opts = ", ".join(str(o)[:50] for o in q.get("options", [])[:4])
        items += f"ID:{q['id']}|Q:{q.get('question','')}|Opts:{opts}|Ans:{q.get('correct','')}\n"
    return f"""Translate these German B1 exam questions to Spanish. For each:
- question_es: Spanish translation of the question
- explanation_es: 1-2 sentences why the answer is correct (Spanish)
- vocabulary: 3-4 key German→Spanish word pairs

Return JSON array: [{{"id":"...","question_es":"...","explanation_es":"...","vocabulary":[{{"de":"...","es":"..."}}]}}]

{items}

ONLY valid JSON array, no markdown."""


def process_batch(batch_info):
    idx, batch = batch_info
    results = call_gemini(build_prompt(batch))
    return idx, batch, {r["id"]: r for r in results if "id" in r}


def main():
    with open(DATA) as f:
        questions = json.load(f)

    needs = [q for q in questions if not q.get("question_es")]
    print(f"Remaining: {len(needs)}", flush=True)

    batches = [(i, needs[i:i+BATCH_SIZE]) for i in range(0, len(needs), BATCH_SIZE)]
    done = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process_batch, b): b for b in batches}
        for future in as_completed(futures):
            idx, batch, rmap = future.result()
            for q in batch:
                if q["id"] in rmap:
                    r = rmap[q["id"]]
                    for j, orig in enumerate(questions):
                        if orig["id"] == q["id"]:
                            questions[j]["question_es"] = r.get("question_es", "")
                            questions[j]["explanation_es"] = r.get("explanation_es", questions[j].get("explanation_es", ""))
                            questions[j]["vocabulary"] = r.get("vocabulary", questions[j].get("vocabulary", []))
                            done += 1
                            break
            print(f"  +{len(rmap)} ({done}/{len(needs)})", flush=True)

    with open(DATA, "w") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    
    total_es = sum(1 for q in questions if q.get("question_es"))
    print(f"\nDone! {total_es}/{len(questions)} translated total", flush=True)


if __name__ == "__main__":
    main()
