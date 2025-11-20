# WikiGap InfoGap Setup Guide

This branch hosts the InfoGap pipeline, API server, and frontend used for WikiGap. Follow the steps below to bring up a fresh checkout.

---

## 1. Clone & enter repo

```bash
git clone <repo-url>
cd WikiGap/infogap
```

---

## 2. Python environment

Create one virtual environment in the repo root and install all Python packages:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

This single venv is used by the pipeline CLI as well as `backend_api/server.py`.

---

## 3. Frontend deps

```bash
cd frontend
npm install
cd ..
```

Later run `npm run dev` inside `frontend/` to start the UI.

---

## 4. Scratch directory

All artifacts live under `backend/scratch/`. Ensure it exists :

```bash
mkdir -p backend/scratch
```

---

## 5. Environment variables

Create `backend/.env` with at least:

```env
SCRATCH_DIR=./scratch
THE_KEY=<your OpenAI key>
```

Never commit this file.

---

## 6. Running the stack

### API server

```bash
cd backend_api
source ../.venv/bin/activate
python server.py
```

### Frontend

```bash
cd frontend
npm run dev
```

### Scraper & pipeline (CLI Manual)

```bash
cd backend
source ../.venv/bin/activate
python main_scrape_bios.py scrape-bios
python main_complete_analysis.py run-multiple-topics
```

- First Run may take a while due to model installations. View by pressing View Logs on the Web UI.
- If Flowmason install fails then do:

#### Flowmason

```bash
cd /Users/home/Downloads/test/infogap

# clone flowmason into a folder named 'flowmason' (if you already have it, see below)
git clone https://github.com/smfsamir/flowmason.git flowmason

cd flowmason
git fetch origin
git checkout abstract
git pull origin abstract

# activate your venv then do an editable install
cd /Users/home/Downloads/test/infogap
. .venv/bin/activate
python -m pip install -e ./flowmason
```

---

## 7. Output locations

- `backend/scratch/ethics_annotation_save/wikigap_data/`: raw annotation JSON.
- `backend/scratch/ethics_annotation_save/wikigap_data/csv/`: CSV exports from the pipeline.
- Final JSONs for the WikiGap extension live under `backend/scratch/ethics_annotation_save/wikigap_data/json/`.

Keep `.env`, `scratch/`, and other generated artifacts out of version control. With these steps you’ll have a unified Python env, frontend deps, and storage ready to run InfoGap end-to-end.
