#!/usr/bin/env python3
"""Fix missing/corrupt options in questions.json using Gemini Vision extraction data."""
import json

DATA = "data/questions.json"

# Extracted via Gemini Vision from actual PDF pages
# Format: {exam: {question_number: {options: [...], correct: "X"}}}
FIXES = {
    "NICOLE": {
        21: {"options": ["a) dass", "b) darum", "c) weil"]},
        22: {"options": ["a) seid", "b) sein", "c) sind"]},
        23: {"options": ["a) euch", "b) Ihnen", "c) Sie"]},
        24: {"options": ["a) kennen gelernt", "b) kennen lernen", "c) kennen lernte"]},
        25: {"options": ["a) mochten", "b) möchten", "c) mögen"]},
        26: {"options": ["a) fanden", "b) finden", "c) findet"]},
        27: {"options": ["a) für", "b) von", "c) wegen"]},
        28: {"options": ["a) gezeigt", "b) zeigen", "c) zeigt"]},
        29: {"options": ["a) mich", "b) sich", "c) uns"]},
        30: {"options": ["a) Freundlich", "b) Freundliche", "c) Freundlichen"]},
    },
    "ANDREAS": {
        21: {"options": ["a) das", "b) den", "c) der"]},
        22: {"options": ["a) zu", "b) zum", "c) zur"]},
        23: {"options": ["a) am", "b) im", "c) mit"]},
        24: {"options": ["a) können", "b) könnten", "c) konnte"]},
        25: {"options": ["a) junge", "b) jungen", "c) junges"]},
        26: {"options": ["a) welche", "b) welchen", "c) welcher"]},
        27: {"options": ["a) mir", "b) dir", "c) sich"]},
        28: {"options": ["a) fand", "b) finden", "c) gefunden"]},
        29: {"options": ["a) denen", "b) deren", "c) die"]},
        30: {"options": ["a) Schreibe", "b) Schreiben", "c) Schreibt"]},
    },
    "ANNIKA3": {
        21: {"options": ["a) auf", "b) in", "c) über"]},
        22: {"options": ["a) Mit", "b) Von", "c) Zwischen"]},
        23: {"options": ["a) schöne", "b) schönen", "c) schönes"]},
        24: {"options": ["a) einfach", "b) immer", "c) noch"]},
        25: {"options": ["a) unsere", "b) unserem", "c) unseren"]},
        26: {"options": ["a) natürlich", "b) schön", "c) viele"]},
        27: {"options": ["a) mit", "b) teil", "c) zu"]},
        28: {"options": ["a) unter", "b) neben", "c) vor"]},
        29: {"options": ["a) bald", "b) bereits", "c) unbedingt"]},
        30: {"options": ["a) noch", "b) schon", "c) schnell"]},
    },
    "CAROLINA": {
        21: {"options": ["a) erzähle", "b) erzählen", "c) erzählt"]},
        22: {"options": ["a) diese", "b) diesen", "c) dieses"]},
        23: {"options": ["a) aber", "b) obwohl", "c) sondern"]},
        24: {"options": ["a) an", "b) für", "c) vor"]},
        25: {"options": ["a) als", "b) wann", "c) wenn"]},
        26: {"options": ["a) denn", "b) ganz", "c) schon"]},
        27: {"options": ["a) früher", "b) jetzt", "c) seit"]},
        28: {"options": ["a) unterschied", "b) unterschiede", "c) unterschieden"]},
        29: {"options": ["a) brauchen", "b) haben", "c) müssen"]},
        30: {"options": ["a) dem", "b) den", "c) der"]},
    },
    "IRIS1": {
        21: {"options": ["a) bei", "b) nach", "c) zu"]},
        22: {"options": ["a) darauf", "b) darum", "c) dazu"]},
        23: {"options": ["a) halbe", "b) halben", "c) halbes"]},
        24: {"options": ["a) Aber", "b) Sondern", "c) Trotzdem"]},
        25: {"options": ["a) hätte", "b) wäre", "c) würde"]},
        26: {"options": ["a) am meisten", "b) ganz", "c) mehr"]},
        27: {"options": ["a) auch", "b) noch", "c) nur"]},
        28: {"options": ["a) als", "b) wann", "c) wenn"]},
        29: {"options": ["a) darf", "b) soll", "c) will"]},
        30: {"options": ["a) das", "b) die", "c) der"]},
    },
    "JENNIFER": {
        21: {"options": ["a) den", "b) der", "c) des"]},
        22: {"options": ["a) mein", "b) mich", "c) mir"]},
        23: {"options": ["a) besondere", "b) besonderem", "c) besonderen"]},
        24: {"options": ["a) durch", "b) für", "c) mit"]},
        25: {"options": ["a) beeindrucken", "b) beeindruckend", "c) beeindruckt"]},
        26: {"options": ["a) am", "b) im", "c) zum"]},
        27: {"options": ["a) Aber", "b) Außer", "c) Außerdem"]},
        28: {"options": ["a) erlauben", "b) erlaubt", "c) erlaubte"]},
        29: {"options": ["a) Einige", "b) Einigen", "c) Einiges"]},
        30: {"options": ["a) mitgenommen", "b) mitnehmen", "c) mitzunehmen"]},
    },
    "TAMARA": {
        21: {"options": ["a) ihnen", "b) Ihnen", "c) Sie"]},
        22: {"options": ["a) das", "b) was", "c) wie"]},
        23: {"options": ["a) Danach", "b) Obwohl", "c) Nämlich"]},
        24: {"options": ["a) für", "b) mit", "c) zu"]},
        25: {"options": ["a) erst", "b) nach", "c) seit"]},
        26: {"options": ["a) besonders", "b) sondern", "c) sonst"]},
        27: {"options": ["a) der", "b) deren", "c) die"]},
        28: {"options": ["a) für", "b) um", "c) zu"]},
        29: {"options": ["a) an", "b) bei", "c) vor"]},
        30: {"options": ["a) mich", "b) mir", "c) sich"]},
    },
    "THOMAS": {
        21: {"options": ["a) ihnen", "b) Ihnen", "c) Sie"]},
        22: {"options": ["a) hat", "b) war", "c) wäre"]},
        23: {"options": ["a) Danach", "b) Obwohl", "c) Nämlich"]},
        24: {"options": ["a) für", "b) mit", "c) zu"]},
        25: {"options": ["a) erst", "b) jetzt", "c) schon"]},
        26: {"options": ["a) besonders", "b) sondern", "c) sonst"]},
        27: {"options": ["a) den", "b) der", "c) die"]},
        28: {"options": ["a) für", "b) um", "c) zu"]},
        29: {"options": ["a) an", "b) bei", "c) vor"]},
        30: {"options": ["a) mich", "b) mir", "c) sich"]},
    },
}

# ANDREAS2 SB1 = same as ANDREAS (confirmed by PDF answer key)
FIXES["ANDREAS2"] = {}
for qn in range(21, 31):
    FIXES["ANDREAS2"][qn] = FIXES["ANDREAS"][qn].copy()


def normalize_option(opt):
    """Normalize option format to 'A) text'."""
    # Input: 'a) text' -> 'A) text'
    if len(opt) >= 2 and opt[1] == ')':
        return opt[0].upper() + opt[1:]
    return opt


with open(DATA) as f:
    data = json.load(f)

fixed = 0
corrupted_fixed = 0

for q in data:
    exam = q.get("exam")
    num = q.get("number")
    if exam in FIXES and num in FIXES[exam]:
        fix = FIXES[exam][num]
        new_opts = [normalize_option(o) for o in fix["options"]]
        old_opts = q.get("options", [])
        
        if not old_opts:
            q["options"] = new_opts
            fixed += 1
            print(f"  FIXED (empty): {exam} Q{num}")
        else:
            # Check if old options are corrupted (contain mixed data)
            old_joined = " ".join(str(o) for o in old_opts)
            if len(old_joined) > 100 or any(len(str(o)) > 40 for o in old_opts):
                q["options"] = new_opts
                corrupted_fixed += 1
                print(f"  FIXED (corrupt): {exam} Q{num}: was {old_opts[:2]}...")
            else:
                # Options exist and look OK - still overwrite with Vision data (more accurate)
                if old_opts != new_opts:
                    q["options"] = new_opts
                    corrupted_fixed += 1
                    print(f"  FIXED (overwrite): {exam} Q{num}")

# Also fix correct answer format for ANDREAS (lowercase -> uppercase)
for q in data:
    if isinstance(q.get("correct"), str) and len(q["correct"]) == 1:
        q["correct"] = q["correct"].upper()

with open(DATA, "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\nDone: {fixed} empty fixed, {corrupted_fixed} corrupted/overwritten")
