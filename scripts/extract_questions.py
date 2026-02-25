#!/usr/bin/env python3
import json
import re
from pathlib import Path

SRC = Path("telc-b1.txt")
OUT = Path("data/questions.json")


def clean_line(s: str) -> str:
    s = s.replace("\x0c", " ").replace("\u200f", " ").replace("\u200e", " ")
    s = s.replace("\u202a", " ").replace("\u202c", " ")
    s = re.sub(r"[\u0600-\u06FF]+", " ", s)  # remove Arabic chars
    s = s.replace("\t", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_lines(lines):
    return [clean_line(x.rstrip("\n")) for x in lines]


def find_exams(lines):
    sol_idx = [i for i, l in enumerate(lines) if l == "Lösungen"]
    exams_raw = []
    for si in sol_idx:
        name = "UNKNOWN"
        for j in range(si - 1, max(-1, si - 25), -1):
            t = lines[j]
            if not t:
                continue
            if t in {"ABDELLAH FARHAN", "LANGUAGE Tests"}:
                continue
            if re.fullmatch(r"[A-ZÄÖÜ0-9]{3,}", t):
                name = t
                break
        exams_raw.append({"name": name, "solution_start": si})

    exams = []
    prev_sol = -1
    for ex in exams_raw:
        name = ex["name"]
        si = ex["solution_start"]
        cstart = None
        for i in range(prev_sol + 1, si):
            if lines[i] == name:
                win = lines[i : min(i + 60, si)]
                if any(re.search(r"Leseverstehen,\s*Teil\s*1", w, re.IGNORECASE) for w in win):
                    cstart = i
                    break
        if cstart is None:
            cstart = prev_sol + 1
        exams.append(
            {
                "name": name,
                "content_start": cstart,
                "content_end": si,
                "solution_start": si,
            }
        )
        prev_sol = si

    for i in range(len(exams)):
        exams[i]["solution_end"] = exams[i + 1]["content_start"] if i + 1 < len(exams) else len(lines)
    return exams


def find_section_bounds(block, pat):
    idxs = [i for i, l in enumerate(block) if re.search(pat, l, re.IGNORECASE)]
    if not idxs:
        return None
    return idxs[0]


def first_idx(block, patterns):
    for i, l in enumerate(block):
        for p in patterns:
            if re.search(p, l, re.IGNORECASE):
                return i
    return None


def parse_solution_map(sol_lines):
    mapping = {}

    # inline patterns like "7 B" or "11-G"
    for line in sol_lines:
        for m in re.finditer(r"(?<!\d)([1-9]|[1-3]\d|40)\s*[-–:]?\s*([A-Za-z])\b", line):
            n = int(m.group(1))
            if n not in mapping:
                mapping[n] = m.group(2)

    # block pairing patterns with OCR column interleaving:
    # collect runs of numbers and runs of one-letter answers, then match by order/length.
    num_runs = []
    ans_runs = []

    i = 0
    while i < len(sol_lines):
        t = sol_lines[i].strip()
        if re.fullmatch(r"([1-9]|[1-5]\d|60)", t):
            start = i
            vals = []
            while i < len(sol_lines) and re.fullmatch(r"([1-9]|[1-5]\d|60)", sol_lines[i].strip()):
                vals.append(int(sol_lines[i].strip()))
                i += 1
            num_runs.append({"start": start, "end": i - 1, "vals": vals})
            continue
        if re.fullmatch(r"[A-Za-z]", t):
            start = i
            vals = []
            while i < len(sol_lines) and re.fullmatch(r"[A-Za-z]", sol_lines[i].strip()):
                vals.append(sol_lines[i].strip())
                i += 1
            ans_runs.append({"start": start, "vals": vals, "used": 0})
            continue
        i += 1

    def plausible(num, letter):
        u = letter.upper()
        if 21 <= num <= 30:
            return u in {"A", "B", "C"}
        if 31 <= num <= 40:
            return "A" <= u <= "O"
        return u in set("ABCDEFGHIJKLX")

    for run in num_runs:
        nums = [n for n in run["vals"] if 1 <= n <= 40 and n not in mapping]
        if not nums:
            continue
        needed = len(nums)
        best = None
        for ar in ans_runs:
            if ar["start"] <= run["end"]:
                continue
            avail = len(ar["vals"]) - ar["used"]
            if avail <= 0:
                continue
            take = min(needed, avail)
            sample = ar["vals"][ar["used"] : ar["used"] + take]
            score = sum(1 for n, a in zip(nums[:take], sample) if plausible(n, a))
            ratio = score / max(1, take)
            if ratio < 0.6:
                continue
            dist = ar["start"] - run["end"]
            cand = (dist, -ratio, ar)
            if best is None or cand < best:
                best = cand
        if best is None:
            continue
        ar = best[2]
        take = min(needed, len(ar["vals"]) - ar["used"])
        sample = ar["vals"][ar["used"] : ar["used"] + take]
        ar["used"] += take
        for n, a in zip(nums[:take], sample):
            if n not in mapping:
                mapping[n] = a

    norm = {}
    for n, a in mapping.items():
        if 21 <= n <= 30:
            norm[n] = a.lower()
        elif 1 <= n <= 40:
            norm[n] = a.upper()
    return norm


def capture_numbered(block, qmin, qmax):
    data = {}
    current = None
    for line in block:
        m = re.match(r"^([0-9]{1,2})\.\s*(.*)$", line)
        if m:
            n = int(m.group(1))
            if qmin <= n <= qmax:
                current = n
                data.setdefault(n, [])
                if m.group(2).strip():
                    data[n].append(m.group(2).strip())
                continue
            current = None
        if current is not None:
            if line and line not in {"ABDELLAH FARHAN", "LANGUAGE Tests"}:
                data[current].append(line)
    return {k: " ".join(v).strip() for k, v in data.items()}


def parse_lv1(block):
    options = []
    texts = capture_numbered(block, 1, 5)
    for line in block:
        mm = re.match(r"^([A-Ja-j])[\)\.]\s*(.+)$", line)
        if mm:
            options.append(f"{mm.group(1).upper()}) {mm.group(2).strip()}")
    # OCR variants like "A Ihr" are in SB1; keep only long lines
    options = [o for o in options if len(o) > 6]
    return texts, options


def parse_lv2(block):
    q = capture_numbered(block, 6, 10)
    return q


def parse_lv3(block):
    q = capture_numbered(block, 11, 20)
    return q


def parse_sb2_word_bank(block):
    bank = []
    seen = set()
    for line in block:
        m = re.match(r"^([a-oA-O])[\)\.]?\s+([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-]+)$", line)
        if m:
            k = m.group(1).lower()
            w = m.group(2).upper()
            if k not in seen:
                bank.append(f"{k}) {w}")
                seen.add(k)
    return bank


def extract_exam_questions(exam, lines):
    content = lines[exam["content_start"]:exam["content_end"]]
    sol = lines[exam["solution_start"]:exam["solution_end"]]

    s_lv1 = first_idx(content, [r"Leseverstehen,\s*Teil\s*1"])
    s_lv2 = first_idx(content, [r"Leseverstehen,\s*Teil\s*2"])
    s_lv3 = first_idx(content, [r"Leseverstehen,\s*Teil\s*3"])
    s_sb1 = first_idx(content, [r"Sprach.?austeine,\s*Teil\s*1"])
    s_sb2 = first_idx(content, [r"Sprach.?austeine,\s*Teil\s*2"])
    s_hv = first_idx(content, [r"Hörverstehen,\s*Teil\s*1", r"Schriftlicher Ausdruck"])

    edges = [x for x in [s_lv1, s_lv2, s_lv3, s_sb1, s_sb2, s_hv, len(content)] if x is not None]
    edges = sorted(set(edges))

    def sub(start, end_marker_candidates):
        if start is None:
            return []
        ends = [x for x in end_marker_candidates if x is not None and x > start]
        end = min(ends) if ends else len(content)
        return content[start:end]

    b_lv1 = sub(s_lv1, [s_lv2, s_lv3, s_sb1, s_hv, len(content)])
    b_lv2 = sub(s_lv2, [s_lv3, s_sb1, s_hv, len(content)])
    b_lv3 = sub(s_lv3, [s_sb1, s_hv, len(content)])
    b_sb1 = sub(s_sb1, [s_sb2, s_hv, len(content)])
    b_sb2 = sub(s_sb2, [s_hv, len(content)])

    answers = parse_solution_map(sol)

    questions = []
    exam_id = exam["name"]

    lv1_texts, lv1_opts = parse_lv1(b_lv1)
    lv2_q = parse_lv2(b_lv2)
    lv3_q = parse_lv3(b_lv3)
    sb2_bank = parse_sb2_word_bank(b_sb2)

    instr_lv1 = next((l for l in b_lv1 if "Überschriften" in l), "Finden Sie für jeden Text die passende Überschrift.")
    instr_lv2 = next((l for l in b_lv2 if "Welche Lösung" in l), "Welche Lösung (a, b oder c) ist jeweils richtig?")
    instr_lv3 = next((l for l in b_lv3 if "Situationen" in l), "Finden Sie für jede Situation die passende Anzeige.")
    instr_sb1 = next((l for l in b_sb1 if "Lücken" in l), "Schließen Sie die Lücken 21-30.")
    instr_sb2 = next((l for l in b_sb2 if "Lücken" in l), "Schließen Sie die Lücken 31-40.")

    for n in range(1, 6):
        qtxt = lv1_texts.get(n, "")
        flags = []
        if not qtxt:
            flags.append("ocr_missing_text")
        if answers.get(n, "?") == "?":
            flags.append("missing_answer_key")
        questions.append({
            "id": f"{exam_id.lower()}-lv1-{n}",
            "exam": exam_id,
            "section": "Leseverstehen",
            "teil": 1,
            "type": "matching",
            "number": n,
            "instruction": instr_lv1,
            "context": qtxt,
            "question": f"Welche Überschrift passt zu Text {n}?",
            "options": lv1_opts if lv1_opts else [f"{c})" for c in "ABCDEFGHIJ"],
            "correct": answers.get(n, "?"),
            "explanation_es": "",
            "vocabulary": [],
            "flags": flags,
        })

    for n in range(6, 11):
        raw = lv2_q.get(n, "")
        flags = []
        if not raw:
            flags.append("ocr_missing_text")
        if answers.get(n, "?") == "?":
            flags.append("missing_answer_key")
        # attempt to split options
        opts = {}
        for m in re.finditer(r"\b([ABC])\s+([^ABC]+?)(?=(\b[ABC]\s+)|$)", raw):
            opts[m.group(1)] = m.group(2).strip()
        if len(opts) < 3:
            options = ["A", "B", "C"]
        else:
            options = [f"{k}) {opts[k]}" for k in ["A", "B", "C"]]
        qtext = raw
        if len(opts) >= 1:
            qtext = re.split(r"\bA\s+", raw)[0].strip() or raw
        questions.append({
            "id": f"{exam_id.lower()}-lv2-{n}",
            "exam": exam_id,
            "section": "Leseverstehen",
            "teil": 2,
            "type": "multiple_choice",
            "number": n,
            "instruction": instr_lv2,
            "context": " ".join([l for l in b_lv2 if l and not re.match(r"^([6-9]|10)\.", l)])[:2500],
            "question": qtext,
            "options": options,
            "correct": answers.get(n, "?"),
            "explanation_es": "",
            "vocabulary": [],
            "flags": flags,
        })

    lv3_opts = [f"{c}" for c in list("ABCDEFGHIJKL") + ["X"]]
    for n in range(11, 21):
        qtxt = lv3_q.get(n, "")
        flags = []
        if not qtxt:
            flags.append("ocr_missing_text")
        if answers.get(n, "?") == "?":
            flags.append("missing_answer_key")
        questions.append({
            "id": f"{exam_id.lower()}-lv3-{n}",
            "exam": exam_id,
            "section": "Leseverstehen",
            "teil": 3,
            "type": "matching",
            "number": n,
            "instruction": instr_lv3,
            "context": "Anzeigen a-l (OCR teilweise unklar).",
            "question": qtxt if qtxt else f"Situation {n}",
            "options": lv3_opts,
            "correct": answers.get(n, "?"),
            "explanation_es": "",
            "vocabulary": [],
            "flags": flags,
        })

    sb1_ctx = " ".join([l for l in b_sb1 if l and not re.match(r"^(2[1-9]|30)\.", l)])[:2500]
    for n in range(21, 31):
        flags = []
        if (answers.get(n, "?").lower() if answers.get(n) else "?") == "?":
            flags.append("missing_answer_key")
        questions.append({
            "id": f"{exam_id.lower()}-sb1-{n}",
            "exam": exam_id,
            "section": "Sprachbausteine",
            "teil": 1,
            "type": "gap_fill",
            "number": n,
            "instruction": instr_sb1,
            "context": sb1_ctx,
            "question": f"Completa el hueco ({n}) con la opción correcta.",
            "options": ["a", "b", "c"],
            "correct": answers.get(n, "?").lower() if answers.get(n) else "?",
            "explanation_es": "",
            "vocabulary": [],
            "flags": flags,
        })

    if not sb2_bank:
        sb2_bank = [f"{chr(96+i)})" for i in range(1, 16)]
    sb2_ctx = " ".join([l for l in b_sb2 if l and not re.match(r"^(3[1-9]|40)\.", l)])[:2500]
    for n in range(31, 41):
        flags = []
        if answers.get(n, "?") == "?":
            flags.append("missing_answer_key")
        questions.append({
            "id": f"{exam_id.lower()}-sb2-{n}",
            "exam": exam_id,
            "section": "Sprachbausteine",
            "teil": 2,
            "type": "word_bank",
            "number": n,
            "instruction": instr_sb2,
            "context": sb2_ctx,
            "question": f"Elige la palabra correcta para el hueco ({n}).",
            "options": sb2_bank,
            "correct": answers.get(n, "?"),
            "explanation_es": "",
            "vocabulary": [],
            "flags": flags,
        })

    return questions


def main():
    raw = SRC.read_text(encoding="utf-8", errors="ignore").splitlines()
    lines = clean_lines(raw)
    exams = find_exams(lines)
    all_questions = []
    for ex in exams:
        all_questions.extend(extract_exam_questions(ex, lines))

    # stable order
    all_questions.sort(key=lambda q: (q["exam"], q["number"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_questions, ensure_ascii=False, indent=2), encoding="utf-8")

    # stats
    missing = sum(1 for q in all_questions if q["correct"] == "?")
    flagged = sum(1 for q in all_questions if q.get("flags"))
    print(f"exams={len(exams)} questions={len(all_questions)} missing_answers={missing} flagged={flagged}")


if __name__ == "__main__":
    main()
