# telc B1 Exam Trainer — PWA

## Goal
Build a mobile-first PWA that helps the user memorize and practice telc Deutsch B1 exam questions. The user's current German level is A2. The strategy is to memorize the exam patterns, not "learn German properly."

## Source Material
- `telc-b1-pruefungsbuch.pdf` — 234-page PDF with ~16 complete telc B1 model exams
- `telc-b1.txt` — extracted text from the PDF (12,275 lines)
- Each exam contains: Leseverstehen (3 Teile), Sprachbausteine (2 Teile), Hörverstehen (3 Teile), Schriftlicher Ausdruck
- Answer keys are included at the end of each exam section (look for lines with just "Lösungen")
- **Skip Hörverstehen** (no audio files available) and **Schriftlicher Ausdruck** (free-form writing)
- Focus on: Leseverstehen (Teil 1, 2, 3) + Sprachbausteine (Teil 1, 2) = ~40 questions per exam × 16 exams = ~640 questions

## Architecture

### Step 1: Extract Questions to JSON
Parse `telc-b1.txt` to extract all questions into structured JSON. Each question needs:
```json
{
  "id": "petra-lv1-1",
  "exam": "PETRA",
  "section": "Leseverstehen",
  "teil": 1,
  "type": "matching|multiple_choice|gap_fill|word_bank",
  "instruction": "...",
  "context": "the reading text or texts",
  "question": "the specific question",
  "options": ["a", "b", "c"] or ["a"..."j"],
  "correct": "b",
  "explanation_es": "Pre-generated Spanish explanation of why this is correct",
  "vocabulary": [{"de": "German word", "es": "Spanish translation"}]
}
```

The PDF text is messy (OCR artifacts, Arabic text mixed in, inconsistent formatting). You'll need to handle this carefully. Key patterns:
- Exam names appear before "Leseverstehen, Teil 1" (e.g., PETRA, ANDREAS, etc.)
- "ABDELLAH FARHAN" appears as a watermark on most pages — ignore it
- Arabic text appears occasionally — ignore it
- Answer keys appear in sections labeled "Lösungen" with format like "1 J", "2 C", etc.
- Some answers are embedded inline (e.g., "11-G", "12-F" written next to questions)

**IMPORTANT**: The text extraction is imperfect. For questions where the text is garbled or unclear, extract what you can and flag them. Quality > completeness.

### Step 2: Generate Explanations
For each question, generate:
1. **Why the correct answer is correct** (in Spanish, simple language for A2 learner)
2. **Why common wrong answers are wrong** (brief)
3. **Key vocabulary** with Spanish translations
4. **Grammar tip** if relevant (e.g., "Dativ requires 'dem' not 'den'")

You can use the Gemini API for this. The API key is available as `GEMINI_API_KEY` environment variable.
Use model `gemini-2.5-flash` via REST API:
```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=$GEMINI_API_KEY
```

Process in batches to avoid rate limits. Save explanations into the question JSON.

### Step 3: Build the PWA
**Tech stack:** Pure HTML/CSS/JS (no frameworks, no build tools). Single `index.html` + `app.js` + `style.css` + `manifest.json` + `sw.js`

**Features:**
1. **Quiz Mode** — presents questions one at a time, randomized order
   - Show the reading text/context
   - Show the question and options
   - On answer: immediately show if correct/incorrect
   - If incorrect: show explanation in Spanish + correct answer
   - Tap any German word to see Spanish translation (use vocabulary data)
2. **Exam Mode** — simulate a full exam (40 questions, timed)
3. **Review Mode** — browse all questions, see explanations
4. **Spaced Repetition** — questions answered wrong appear 2x more often
5. **Progress Tracking** — localStorage: which questions mastered, accuracy per section, streak
6. **Offline** — service worker caches everything, works without internet
7. **Install** — PWA manifest so it can be added to home screen

**UI/UX:**
- Mobile-first (375px width primary target)
- Dark mode default (easier on eyes for study sessions)
- Large touch targets (44px minimum)
- Swipe to navigate between questions
- Bottom nav: Quiz | Exam | Review | Progress
- Language: UI in Spanish (user's native language), content in German (learning target)
- Clean, minimal design — no clutter

**Question Type Rendering:**
- **Leseverstehen Teil 1** (matching): Show texts + list of titles. User matches each text to a title.
- **Leseverstehen Teil 2** (multiple choice): Show long text + questions with a/b/c options.
- **Leseverstehen Teil 3** (matching): Show situations + classified ads. User matches situations to ads.
- **Sprachbausteine Teil 1** (gap fill): Show letter with gaps, user picks a/b/c for each gap.
- **Sprachbausteine Teil 2** (word bank): Show text with gaps + word list. User fills gaps from word bank.

## Output
All files in this directory (`/home/claude-agent/telc-b1-app/`):
- `data/questions.json` — all extracted questions with explanations
- `index.html` — main app
- `app.js` — app logic
- `style.css` — styles
- `manifest.json` — PWA manifest
- `sw.js` — service worker
- `icons/` — app icons (generate simple ones)

## Constraints
- NO frameworks, NO npm, NO build tools — pure vanilla JS
- Must work offline after first load
- All question data baked into a single JSON file (loaded by the app)
- Mobile-first responsive design
- UI language: Spanish
- Content language: German
- Explanations in Spanish
