#!/usr/bin/env python3
import json
import os
import re
import time
import urllib.request
from pathlib import Path

INPUT = Path("data/questions.json")
BATCH_SIZE = 8
DELAY_SECONDS = 1.4


def call_gemini(api_key: str, payload: dict) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_json(text: str):
    text = text.strip()
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        m = re.search(r"(\{.*\})", text, re.S)
        if m:
            text = m.group(1)
    return json.loads(text)


def local_fallback(q):
    if q.get("correct") == "?":
        exp = "El OCR no permite ver la clave con seguridad. Revisa el contexto y elimina opciones que no encajan en significado o gramática."
    else:
        exp = f"La respuesta correcta es {q['correct']}. Encaja mejor con el contexto del ejercicio y la intención comunicativa de la frase/texto."
    vocab = []
    for token in re.findall(r"[A-Za-zÄÖÜäöüß]{5,}", q.get("question", ""))[:3]:
        vocab.append({"de": token, "es": "(revisar significado)"})
    return exp, vocab


def build_prompt(batch):
    compact = []
    for q in batch:
        compact.append(
            {
                "id": q["id"],
                "tipo": f"{q['section']} T{q['teil']} {q['type']}",
                "pregunta": q["question"],
                "opciones": q["options"][:15],
                "correcta": q["correct"],
                "contexto": (q.get("context") or "")[:600],
            }
        )

    system = (
        "Eres profesor de alemán para hispanohablantes nivel A2. "
        "Devuelve SOLO JSON válido con este formato exacto: "
        "{\"results\":[{\"id\":\"...\",\"explanation_es\":\"...\",\"vocabulary\":[{\"de\":\"...\",\"es\":\"...\"}]}]}. "
        "Para cada pregunta: explica brevemente por qué la respuesta correcta es correcta, menciona por qué fallan opciones típicas, "
        "y da 3-5 palabras clave. Español simple, frases cortas. Si correcta='?' dilo claramente."
    )
    return {
        "contents": [
            {
                "parts": [
                    {
                        "text": system + "\n\nPreguntas:\n" + json.dumps(compact, ensure_ascii=False)
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }


def main():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    data = json.loads(INPUT.read_text(encoding="utf-8"))

    for i in range(0, len(data), BATCH_SIZE):
        batch = data[i : i + BATCH_SIZE]
        if all(q.get("explanation_es") for q in batch):
            continue

        mapped = {}
        if api_key:
            try:
                payload = build_prompt(batch)
                resp = call_gemini(api_key, payload)
                cands = resp.get("candidates", [])
                text = ""
                if cands:
                    parts = cands[0].get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts)
                parsed = extract_json(text)
                for item in parsed.get("results", []):
                    mapped[item.get("id", "")] = item
            except Exception as e:
                print(f"batch {i//BATCH_SIZE+1}: gemini_error={e}")

        for q in batch:
            item = mapped.get(q["id"])
            if item:
                q["explanation_es"] = (item.get("explanation_es") or "").strip()[:900]
                vocab = item.get("vocabulary") or []
                clean_vocab = []
                for v in vocab[:5]:
                    de = str(v.get("de", "")).strip()
                    es = str(v.get("es", "")).strip()
                    if de and es:
                        clean_vocab.append({"de": de, "es": es})
                q["vocabulary"] = clean_vocab
            else:
                exp, vocab = local_fallback(q)
                q["explanation_es"] = exp
                q["vocabulary"] = vocab

        INPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"batch {i//BATCH_SIZE+1}: processed {min(i+BATCH_SIZE,len(data))}/{len(data)}")
        time.sleep(DELAY_SECONDS)

    print("done")


if __name__ == "__main__":
    main()
