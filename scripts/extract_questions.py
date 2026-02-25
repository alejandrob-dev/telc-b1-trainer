#!/usr/bin/env python3
import json
import re
from collections import defaultdict
from pathlib import Path

SRC = Path("telc-b1.txt")
OUT = Path("data/questions.json")

EXAMS = [
    "ANDREAS", "ANDREAS2", "ANNIKA3", "CAROLINA", "EVA1", "IRIS1", "JAN", "JENNIFER",
    "NADIA2", "NICOLE", "PETRA", "SOPHIE", "TAMARA", "THOMAS", "VERA", "VIKTOR",
]


def clean_line(s: str) -> str:
    s = s.replace("\x0c", " ").replace("\u200f", " ").replace("\u200e", " ")
    s = s.replace("\u202a", " ").replace("\u202c", " ")
    s = re.sub(r"[\u0600-\u06FF]+", " ", s)
    s = s.replace("\t", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def skip_noise(line: str) -> bool:
    if not line:
        return True
    if line in {"LANGUAGE Tests", "ABDELLAH FARHAN", "ANSWER KEY"}:
        return True
    if re.fullmatch(r"\d{1,3}", line):
        return True
    return False


def first_idx(lines, start, end, patterns):
    for i in range(start, end):
        for p in patterns:
            if re.search(p, lines[i], re.IGNORECASE):
                return i
    return None


def find_exam_blocks(lines):
    starts = []
    for exam in EXAMS:
        pos = None
        for i, line in enumerate(lines):
            if line != exam:
                continue
            win = lines[i : i + 20]
            if any(re.search(r"Leseverstehen,\s*Teil\s*1", w, re.IGNORECASE) for w in win):
                pos = i
                break
        if pos is not None:
            starts.append((exam, pos))

    starts = sorted(starts, key=lambda x: x[1])
    blocks = []
    for idx, (name, start) in enumerate(starts):
        end = starts[idx + 1][1] if idx + 1 < len(starts) else len(lines)
        blocks.append({"name": name, "start": start, "end": end})
    return blocks


def parse_answer_map(exam_lines):
    mapping = {}
    for line in exam_lines:
        # 11-G / 10 B / 6C
        for m in re.finditer(r"(?<!\d)([1-9]|[1-3]\d|40)\s*[-–:]?\s*([A-Za-zXx])\b", line):
            n = int(m.group(1))
            mapping[n] = m.group(2).upper()

        # 31 J SCHON / 33 ZWAR (ignore latter if no letter)
        m2 = re.match(r"^([1-9]|[1-3]\d|40)\s+([A-Za-zXx])\b", line)
        if m2:
            mapping[int(m2.group(1))] = m2.group(2).upper()

    for n in range(21, 31):
        if n in mapping:
            mapping[n] = mapping[n].lower()
    return mapping


def section_slices(lines, start, end):
    s_lv1 = first_idx(lines, start, end, [r"Leseverstehen,\s*Teil\s*1"])
    s_lv2 = first_idx(lines, start, end, [r"Leseverstehen,\s*Teil\s*2"])
    s_lv3 = first_idx(lines, start, end, [r"Leseverstehen,\s*Teil\s*3"])
    s_sb1 = first_idx(lines, start, end, [r"Sprach.?austeine,\s*Teil\s*1"])
    s_sb2 = first_idx(lines, start, end, [r"Sprach.?austeine,\s*Teil\s*2"])
    s_hv = first_idx(lines, start, end, [r"Hörverstehen,\s*Teil\s*1", r"Schriftlicher Ausdruck"])

    def slc(s, nxt):
        if s is None:
            return []
        candidates = [x for x in nxt if x is not None and x > s]
        e = min(candidates) if candidates else end
        return lines[s:e]

    return {
        "lv1": slc(s_lv1, [s_lv2, s_lv3, s_sb1, s_sb2, s_hv, end]),
        "lv2": slc(s_lv2, [s_lv3, s_sb1, s_sb2, s_hv, end]),
        "lv3": slc(s_lv3, [s_sb1, s_sb2, s_hv, end]),
        "sb1": slc(s_sb1, [s_sb2, s_hv, end]),
        "sb2": slc(s_sb2, [s_hv, end]),
    }


def capture_numbered(block, qmin, qmax):
    out = defaultdict(list)
    current = None
    for line in block:
        m = re.match(r"^([0-9]{1,2})\.\s*(.*)$", line)
        if m:
            n = int(m.group(1))
            if qmin <= n <= qmax:
                current = n
                if m.group(2).strip():
                    out[n].append(m.group(2).strip())
                continue
            current = None
        if current is not None and not skip_noise(line):
            # stop when obvious answer key stream begins
            if re.match(r"^([1-9]|[1-3]\d|40)\s*[-–:]?\s*[A-Za-zXx]\b", line):
                continue
            out[current].append(line)
    return {k: " ".join(v).strip() for k, v in out.items()}


def parse_lv1(block):
    texts = capture_numbered(block, 1, 5)
    headings = []
    seen = set()
    for line in block:
        m = re.match(r"^([A-Ja-j])[\)\.]\s*(.+)$", line)
        if not m:
            continue
        letter = m.group(1).upper()
        txt = m.group(2).strip()
        if len(txt) < 3:
            continue
        if letter in seen:
            continue
        seen.add(letter)
        headings.append(f"{letter}) {txt}")
    return texts, headings


def split_question_segments(block, qmin, qmax):
    points = []
    for i, line in enumerate(block):
        m = re.match(r"^([0-9]{1,2})\.\s*(.*)$", line)
        if m:
            n = int(m.group(1))
            if qmin <= n <= qmax:
                points.append((i, n))
    segs = {}
    for idx, (s, n) in enumerate(points):
        e = points[idx + 1][0] if idx + 1 < len(points) else len(block)
        segs[n] = block[s:e]
    return segs


def parse_abc_segment(seg_lines):
    q_text_parts = []
    options = {"A": [], "B": [], "C": []}
    unlabeled = []
    current = None

    for j, raw in enumerate(seg_lines):
        if skip_noise(raw):
            continue
        if j == 0:
            m = re.match(r"^[0-9]{1,2}\.\s*(.*)$", raw)
            if m and m.group(1).strip():
                q_text_parts.append(m.group(1).strip())
            continue

        lab = re.match(r"^([A-Ca-c])[\)\.]?\s*(.*)$", raw)
        if lab:
            current = lab.group(1).upper()
            tail = lab.group(2).strip()
            if tail:
                options[current].append(tail)
            continue

        if re.match(r"^([1-9]|[1-3]\d|40)\s*[-–:]?\s*[A-Za-zXx]\b", raw):
            continue

        if current in {"A", "B", "C"}:
            options[current].append(raw)
        else:
            unlabeled.append(raw)

    # OCR often loses B label; use one unlabeled line as B if needed
    if not options["B"] and unlabeled:
        options["B"].append(unlabeled[0])
        if len(unlabeled) > 1:
            q_text_parts.extend(unlabeled[1:])
    else:
        q_text_parts.extend(unlabeled)

    q_text = " ".join(q_text_parts).strip()
    out_opts = []
    for k in ["A", "B", "C"]:
        txt = " ".join(options[k]).strip()
        if txt:
            out_opts.append(f"{k}) {txt}")
    return q_text, out_opts


def parse_lv2(block):
    segments = split_question_segments(block, 6, 10)
    parsed = {}
    for n in range(6, 11):
        seg = segments.get(n, [])
        q_text, opts = parse_abc_segment(seg)
        parsed[n] = {"question": q_text, "options": opts}
    return parsed


def parse_lv3(block):
    situations = capture_numbered(block, 11, 20)

    first_sit = None
    for i, line in enumerate(block):
        if re.match(r"^11\.\s+", line):
            first_sit = i
            break

    ads_region = block[:first_sit] if first_sit is not None else []
    ads = {}
    current = None
    for line in ads_region:
        if skip_noise(line):
            continue
        m = re.match(r"^([A-La-l])[\)\.]\s*(.+)$", line)
        if m:
            current = m.group(1).upper()
            ads[current] = [m.group(2).strip()]
            continue
        if current and not re.search(r"Lesen sie die Situationen|Markieren", line, re.IGNORECASE):
            if not re.match(r"^\d+\.\s", line):
                ads[current].append(line)

    ad_options = []
    for letter in "ABCDEFGHIJKL":
        if letter in ads:
            txt = " ".join(ads[letter]).strip()
            if txt:
                ad_options.append(f"{letter}) {txt}")
    if ad_options:
        ad_options.append("X) Keine passende Anzeige")

    return situations, ad_options, (len(ad_options) <= 1)


def parse_sb1(block):
    segments = split_question_segments(block, 21, 30)
    parsed = {}
    for n in range(21, 31):
        q_text, opts = parse_abc_segment(segments.get(n, []))
        parsed[n] = {"question": q_text, "options": opts}

    # fallback for OCR column chaos: infer grouped options near explicit number labels
    if sum(1 for n in range(21, 31) if len(parsed[n]["options"]) == 3) < 6:
        # collect every option token in block
        tokens = []
        for line in block:
            m = re.match(r"^([A-Ca-c]{1,2})\s+(.+)$", line)
            if m:
                lbl = m.group(1)[0].upper()
                txt = m.group(2).strip()
                if txt and not re.match(r"^\d+\.?$", txt):
                    tokens.append((lbl, txt))
        # assign first complete triplets sequentially to missing questions
        triplets = []
        i = 0
        while i < len(tokens):
            bucket = {}
            while i < len(tokens) and len(bucket) < 3:
                lbl, txt = tokens[i]
                if lbl not in bucket:
                    bucket[lbl] = txt
                i += 1
            if len(bucket) == 3:
                triplets.append(bucket)
        ti = 0
        for n in range(21, 31):
            if len(parsed[n]["options"]) == 3:
                continue
            if ti >= len(triplets):
                break
            t = triplets[ti]
            ti += 1
            parsed[n]["options"] = [f"A) {t['A']}", f"B) {t['B']}", f"C) {t['C']}"]

    return parsed


def parse_sb2_word_bank(block):
    bank = {}
    for i, line in enumerate(block):
        # compact format: a) AUCH
        m = re.match(r"^([A-Oa-o])[\)\.]\s*([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\- ]+)$", line)
        if m:
            bank[m.group(1).upper()] = m.group(2).strip().upper()
            continue

        # split-column format: a b c, then next lines with words
        if re.fullmatch(r"[a-oA-O]", line):
            letters = [line.upper()]
            j = i + 1
            while j < min(i + 4, len(block)) and re.fullmatch(r"[a-oA-O]", block[j]):
                letters.append(block[j].upper())
                j += 1
            words = []
            k = j
            while k < min(j + 6, len(block)) and len(words) < len(letters):
                w = block[k].strip()
                if w and not skip_noise(w) and not re.fullmatch(r"[a-oA-O]", w):
                    words.append(w.upper())
                k += 1
            for ltr, word in zip(letters, words):
                bank.setdefault(ltr, word)

    options = [f"{ltr}) {bank[ltr]}" for ltr in "ABCDEFGHIJKLMNO" if ltr in bank]
    return options


def build_exam_questions(exam_name, ex_lines):
    answers = parse_answer_map(ex_lines)
    sections = section_slices(ex_lines, 0, len(ex_lines))

    lv1_texts, lv1_opts = parse_lv1(sections["lv1"])
    lv2 = parse_lv2(sections["lv2"])
    lv3_sit, lv3_opts, ads_missing = parse_lv3(sections["lv3"])
    sb1 = parse_sb1(sections["sb1"])
    sb2_bank = parse_sb2_word_bank(sections["sb2"])

    qs = []

    instr_lv1 = "Finden Sie für jeden Text die passende Überschrift."
    instr_lv2 = "Welche Lösung (a, b oder c) ist jeweils richtig?"
    instr_lv3 = "Finden Sie für jede Situation die passende Anzeige."
    instr_sb1 = "Schließen Sie die Lücken 21–30."
    instr_sb2 = "Schließen Sie die Lücken 31–40 mit dem Wortschatzkasten."

    for n in range(1, 6):
        flags = []
        if not lv1_texts.get(n):
            flags.append("question_text_missing")
        if len(lv1_opts) < 10:
            flags.append("options_missing")
        if n not in answers:
            flags.append("missing_answer_key")
        qs.append({
            "id": f"{exam_name.lower()}-lv1-{n}",
            "exam": exam_name,
            "section": "Leseverstehen",
            "teil": 1,
            "type": "matching",
            "number": n,
            "instruction": instr_lv1,
            "context": lv1_texts.get(n, ""),
            "question": f"Welche Überschrift passt zu Text {n}?",
            "question_es": "",
            "options": lv1_opts,
            "correct": answers.get(n, "?"),
            "explanation_es": "",
            "vocabulary": [],
            "flags": flags,
        })

    context_lv2 = " ".join([l for l in sections["lv2"] if not skip_noise(l)])[:2800]
    for n in range(6, 11):
        item = lv2.get(n, {"question": "", "options": []})
        flags = []
        if not item["question"]:
            flags.append("question_text_missing")
        if len(item["options"]) < 3:
            flags.append("options_missing")
        if n not in answers:
            flags.append("missing_answer_key")
        qs.append({
            "id": f"{exam_name.lower()}-lv2-{n}",
            "exam": exam_name,
            "section": "Leseverstehen",
            "teil": 2,
            "type": "multiple_choice",
            "number": n,
            "instruction": instr_lv2,
            "context": context_lv2,
            "question": item["question"] or f"Aufgabe {n}",
            "question_es": "",
            "options": item["options"],
            "correct": answers.get(n, "?"),
            "explanation_es": "",
            "vocabulary": [],
            "flags": flags,
        })

    # Fallback: when ads couldn't be extracted from OCR, provide letter options
    # so the quiz is still functional (student matches against memorised ad letters)
    if not lv3_opts:
        lv3_opts = [
            "A) Anzeige A", "B) Anzeige B", "C) Anzeige C", "D) Anzeige D",
            "E) Anzeige E", "F) Anzeige F", "G) Anzeige G", "H) Anzeige H",
            "I) Anzeige I", "J) Anzeige J", "K) Anzeige K", "L) Anzeige L",
            "X) Keine passende Anzeige",
        ]

    for n in range(11, 21):
        flags = []
        if not lv3_sit.get(n):
            flags.append("question_text_missing")
        if ads_missing:
            flags.append("ads_missing")
        if n not in answers:
            flags.append("missing_answer_key")
        qs.append({
            "id": f"{exam_name.lower()}-lv3-{n}",
            "exam": exam_name,
            "section": "Leseverstehen",
            "teil": 3,
            "type": "matching",
            "number": n,
            "instruction": instr_lv3,
            "context": "(Die Anzeigentexte sind im OCR nicht vorhanden — siehe Prüfungsbuch S. 2-3)",
            "question": lv3_sit.get(n, f"Situation {n}"),
            "question_es": "",
            "options": lv3_opts,
            "correct": answers.get(n, "?"),
            "explanation_es": "",
            "vocabulary": [],
            "flags": flags,
        })

    context_sb1 = " ".join([l for l in sections["sb1"] if not skip_noise(l)])[:2800]
    for n in range(21, 31):
        item = sb1.get(n, {"question": "", "options": []})
        flags = []
        if len(item["options"]) < 3:
            flags.append("options_missing")
        if n not in answers:
            flags.append("missing_answer_key")
        qs.append({
            "id": f"{exam_name.lower()}-sb1-{n}",
            "exam": exam_name,
            "section": "Sprachbausteine",
            "teil": 1,
            "type": "gap_fill",
            "number": n,
            "instruction": instr_sb1,
            "context": context_sb1,
            "question": item["question"] or f"Lücke {n}",
            "question_es": "",
            "options": item["options"],
            "correct": answers.get(n, "?").lower() if n in answers else "?",
            "explanation_es": "",
            "vocabulary": [],
            "flags": flags,
        })

    context_sb2 = " ".join([l for l in sections["sb2"] if not skip_noise(l)])[:2800]
    for n in range(31, 41):
        flags = []
        if len(sb2_bank) < 10:
            flags.append("options_missing")
        if n not in answers:
            flags.append("missing_answer_key")
        qs.append({
            "id": f"{exam_name.lower()}-sb2-{n}",
            "exam": exam_name,
            "section": "Sprachbausteine",
            "teil": 2,
            "type": "word_bank",
            "number": n,
            "instruction": instr_sb2,
            "context": context_sb2,
            "question": f"Welche Option passt in Lücke {n}?",
            "question_es": "",
            "options": sb2_bank,
            "correct": answers.get(n, "?"),
            "explanation_es": "",
            "vocabulary": [],
            "flags": flags,
        })

    return qs


def verification_reports(questions):
    print("\n=== Verification pass 1: Completeness ===")
    by_exam = defaultdict(list)
    for q in questions:
        by_exam[q["exam"]].append(q)

    for exam in sorted(by_exam):
        rows = by_exam[exam]
        print(f"\n[{exam}] total={len(rows)}")
        for section, teil, start, end in [
            ("Leseverstehen", 1, 1, 5),
            ("Leseverstehen", 2, 6, 10),
            ("Leseverstehen", 3, 11, 20),
            ("Sprachbausteine", 1, 21, 30),
            ("Sprachbausteine", 2, 31, 40),
        ]:
            subset = [q for q in rows if q["section"] == section and q["teil"] == teil]
            nums = sorted(q["number"] for q in subset)
            missing_nums = [n for n in range(start, end + 1) if n not in nums]
            bad_opts = [q["number"] for q in subset if len(q.get("options") or []) == 0]
            partial_opts = [q["number"] for q in subset if 0 < len(q.get("options") or []) < 3 and q["teil"] in {2, 1}]
            flagged = [q["number"] for q in subset if "options_missing" in q.get("flags", []) or "ads_missing" in q.get("flags", [])]
            print(
                f"  {section} T{teil}: count={len(subset)} missing_q={missing_nums} "
                f"no_opts={bad_opts} partial_opts={partial_opts} flagged={flagged[:12]}"
            )

    print("\n=== Verification pass 2: Correctness sample ===")
    samples = []
    for q in questions:
        if q["number"] in {1, 6, 11, 21, 31}:
            samples.append(q)

    ok = 0
    for q in samples:
        corr = str(q.get("correct", "?")).strip().upper()[:1]
        opt_keys = {re.match(r"^([A-Za-zXx])", o).group(1).upper() for o in q.get("options", []) if re.match(r"^([A-Za-zXx])", o)}
        valid = corr in opt_keys
        if valid:
            ok += 1
        print(
            f"{q['exam']} #{q['number']} ({q['section']} T{q['teil']}) "
            f"correct={q['correct']} option_keys={''.join(sorted(opt_keys)) or '-'} -> {'OK' if valid else 'MISMATCH'}"
        )
    print(f"Sample matches: {ok}/{len(samples)}")


def main():
    raw = SRC.read_text(encoding="utf-8", errors="ignore").splitlines()
    lines = [clean_line(x) for x in raw]

    exam_blocks = find_exam_blocks(lines)
    all_questions = []

    for ex in exam_blocks:
        ex_lines = lines[ex["start"]:ex["end"]]
        all_questions.extend(build_exam_questions(ex["name"], ex_lines))

    all_questions.sort(key=lambda q: (q["exam"], q["number"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_questions, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"exams={len(exam_blocks)} questions={len(all_questions)}")
    verification_reports(all_questions)


if __name__ == "__main__":
    main()
