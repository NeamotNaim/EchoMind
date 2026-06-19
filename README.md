# EchoMind

> **A multi-agent AI system that preserves the life stories of elderly or dying people as beautiful digital memoirs.**

Built for the **Band of Agents Hackathon 2026** (lablab.ai, June 12–19, 2026).

---

## What it does

A family member — or the person themselves — answers 12 warm, carefully chosen questions about their life. When the interview is complete, **five AI agents collaborate through [Band](https://app.band.ai/)** to turn those raw answers into a polished, downloadable PDF memoir, with a shareable family link and a QR code.

The five agents:

1. **EchoMind Interviewer** — conducts the warm conversation (in the Flask app, via Gemini)
2. **EchoMind Organiser** — sorts the raw transcript into thematic chapters
3. **EchoMind FactChecker** — enriches each memory with historical context (Wikipedia)
4. **EchoMind Storyteller** — transforms the memories into first-person literary prose
5. **EchoMind LegacyBuilder** — assembles the final PDF and announces the share link

A complete **demo memoir for Margaret Rose Williams** is available at `/memoir/demo` — judges can see the full output immediately, no interview required.

---

## Tech stack

| Layer            | Choice                                                        |
| ---------------- | ------------------------------------------------------------- |
| Web              | Flask 3 + Flask-SQLAlchemy                                    |
| LLM              | **Google Gemini 2.5 Flash** via `google-generativeai`         |
| Agent runtime    | **Band** via `band-sdk[google_adk]` (the `GoogleADKAdapter`)  |
| PDF              | ReportLab Platypus                                            |
| QR codes         | `qrcode[pil]`                                                 |
| Historical facts | Wikipedia REST API + DuckDuckGo Instant Answer                |
| Database         | SQLite                                                        |
| Deployment       | Render / Railway (free tier)                                  |

---

## Project structure

```
.
├── app.py                  ← Flask application factory
├── config.py               ← env-driven configuration
├── requirements.txt
├── .env.example            ← copy to .env, fill in your keys
├── agent_config.yaml.example  ← copy to agent_config.yaml, fill in Band credentials
├── agents/
│   ├── _common.py          ← shared helpers (config loader, adapter builder)
│   ├── run_interviewer.py
│   ├── run_organiser.py
│   ├── run_factchecker.py
│   ├── run_storyteller.py
│   └── run_legacybuilder.py
├── models/database.py      ← SQLAlchemy Session + Memoir
├── utils/
│   ├── gemini_client.py    ← Flask-side Gemini wrapper
│   ├── pdf_generator.py
│   ├── qr_generator.py
│   └── history_lookup.py
├── routes/
│   ├── main.py             ← landing page + start session
│   ├── session.py          ← interview + /api/build-memoir
│   └── memoir.py           ← viewer + download + /memoir/demo
├── templates/              ← base, index, session, waiting, memoir
└── static/                 ← css, js, generated memoirs + qr codes
```

---

## Quick start

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
cp agent_config.yaml.example agent_config.yaml
```

Edit both files:

**`.env`** — at minimum, set `GOOGLE_API_KEY` (free at [aistudio.google.com](https://aistudio.google.com)):

```dotenv
GOOGLE_API_KEY=your_google_api_key_here
THENVOI_REST_URL=https://app.band.ai/
THENVOI_WS_URL=wss://app.band.ai/api/v1/socket/websocket
SECRET_KEY=echomind-hackathon-2026-secret
DATABASE_URL=sqlite:///echomind.db
BASE_URL=http://localhost:5000
DEMO_MODE=True
```

**`agent_config.yaml`** — for each of the 5 agents, paste the `agent_id` (UUID) and `api_key` from your [app.band.ai/agents](https://app.band.ai/agents) dashboard. The UUID is shown in the bottom-right of each agent's page; the API key was shown once when you created the agent.

```yaml
interviewer:
  agent_id: "..."
  api_key:  "..."
organiser:
  agent_id: "..."
  api_key:  "..."
# ... and so on for factchecker, storyteller, legacybuilder
```

### 3. Run

EchoMind has **two parts** that run side by side:

**Part A — the Flask web app** (interview UI + memoir viewer + `/api/build-memoir`):

```bash
python app.py
```

Open <http://localhost:5000>.

**Part B — the five Band agents** (each in its own terminal, or background process):

```bash
python agents/run_interviewer.py
python agents/run_organiser.py
python agents/run_factchecker.py
python agents/run_storyteller.py
python agents/run_legacybuilder.py
```

Each agent connects to Band over WebSocket and sits in the same room, waiting for its `@mention`. The Band room transcript is itself a deliverable — judges can watch the 5 agents coordinate in real time.

### 4. (Optional) Override Band credentials via env vars

Instead of `agent_config.yaml`, you can set:

```bash
export ECHOMIND_INTERVIEWER_AGENT_ID=...
export ECHOMIND_INTERVIEWER_API_KEY=...
# ... and so on for the other four agents
```

---

## How a session flows

1. User opens `/` and submits the start form (`subject_name`, optional `birth_year`, optional `location`).
2. A new `Session` row is created with `status='active'` and an empty `conversation_json`.
3. User is redirected to `/session/<id>`. The Flask app calls **Gemini** for each follow-up question (or uses the scripted list if no key is set). The transcript is stored as JSON in `conversation_json`.
4. After 15 exchanges the interview is marked complete. The Flask app posts the transcript to the Band room and tags the **Organiser** agent. `Session.status` → `processing`.
5. The 5 Band agents take over:
   - **Organiser** classifies the memories into 8 chapters, tags **FactChecker**
   - **FactChecker** enriches each memory with Wikipedia context, tags **Storyteller**
   - **Storyteller** writes 300–500 words of literary prose per chapter, tags **LegacyBuilder**
   - **LegacyBuilder** calls Flask's `POST /api/build-memoir`, gets back the share URL, announces it in the Band room
6. The waiting page polls `/session/<id>/memoir-token` and redirects to `/memoir/<token>` when ready.

---

## Routes

| Method | Path                                  | Purpose                                |
| ------ | ------------------------------------- | -------------------------------------- |
| GET    | `/`                                   | Landing page                           |
| POST   | `/start`                              | Create a new session                   |
| GET    | `/session/<id>`                       | Interview UI                           |
| POST   | `/session/<id>/message`               | Send an answer, get the next question  |
| GET    | `/session/<id>/status`                | JSON status                            |
| GET    | `/session/<id>/waiting`               | Pipeline progress screen               |
| GET    | `/session/<id>/memoir-token`          | JSON: share token when ready           |
| POST   | `/api/build-memoir`                   | Called by the LegacyBuilder agent      |
| GET    | `/memoir/<token>`                     | Memoir viewer                          |
| GET    | `/memoir/<token>/download`            | PDF download                           |
| GET    | `/memoir/demo`                        | Margaret Williams demo (hardcoded)     |

---

## Environment variables

See [`.env.example`](.env.example) for the full list. Key ones:

- **`GOOGLE_API_KEY`** — required for the Flask-side interviewer to use Gemini. If missing, the interviewer uses its 12-question scripted list as a fallback (so the app still works for the demo).
- **`BASE_URL`** — used to build share links and QR codes. Set to your deployment URL in production.
- **`DEMO_MODE`** — informational only; `/memoir/demo` always renders the hardcoded Margaret Williams chapters.
- **`THENVOI_REST_URL`** / **`THENVOI_WS_URL`** — Band endpoints. Defaults are correct; only change if instructed.

---

## Notes on the agent architecture

Each Band agent is a **standalone Python process**. They use the `GoogleADKAdapter` from the `band-sdk[google_adk]` extra, which wraps Google's Agent Development Kit and gives each agent:

- A Gemini 2.5 Flash model
- A `custom_section` system prompt (defined in each `run_*.py` file)
- A list of `thenvoi_send_message` platform tools
- For the LegacyBuilder, an `additional_tools` entry that calls back into Flask's `/api/build-memoir`

The agents are intentionally thin — the heavy work (organising, enriching, writing) is done by Gemini in the Band room. The Flask app only handles the human-facing interview, the final PDF assembly, and the viewer.

If the `thenvoi` package is not yet published to PyPI, install it from the source documented in the hackathon materials; if it's not yet available at all, the Flask app still runs and the demo works — the agents just won't be able to connect to Band.
