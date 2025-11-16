"""
Local API server that wraps CLI commands for the frontend.
Runs on localhost only - user clones repo and runs this locally.
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import os
from pathlib import Path
import threading
import shutil
import time
import uuid
import re
from textwrap import indent
from dotenv import load_dotenv

app = FastAPI()

# Allow CORS for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get directories
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
ENV_PATH = BACKEND_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

SCRATCH_DIR = os.environ.get("SCRATCH_DIR")
if not SCRATCH_DIR:
    SCRATCH_DIR = str((BACKEND_DIR / "scratch").resolve())
    os.environ["SCRATCH_DIR"] = SCRATCH_DIR

WIKIGAP_TOPICS_FILE = BACKEND_DIR / "wikigap_topics_scrape.py"
CONSTANTS_FILE = BACKEND_DIR / "packages" / "constants.py"

# In-memory job store (simple placeholder; replace with persistent store/queue later)
JOBS: dict[str, dict] = {}


def resolve_python_executable() -> str:
    """Return the preferred python executable (root .venv if available)."""
    venv_dir = ROOT_DIR / ".venv"
    if os.name == "nt":
        candidate = venv_dir / "Scripts" / "python.exe"
    else:
        candidate = venv_dir / "bin" / "python"
    if candidate.exists():
        return str(candidate)

    legacy = BACKEND_DIR / ".venv" / "bin" / "python"
    if legacy.exists():
        return str(legacy)

    return shutil.which("python") or "python"


def write_topics_file(topics: list[str]) -> None:
    """Persist topics inside backend/wikigap_topics_scrape.py."""
    serialized = ",\n".join(f"{repr(topic)}" for topic in topics)
    contents = "selected_topics = [\n"
    if serialized:
        contents += indent(serialized, "    ")
        contents += ",\n"
    contents += "]\n"
    WIKIGAP_TOPICS_FILE.write_text(contents, encoding="utf-8")


def update_tgt_lang_constant(tgt_lang: str) -> None:
    """Set TGT_LANG in packages/constants.py."""
    text = CONSTANTS_FILE.read_text(encoding="utf-8")
    new_text, substituted = re.subn(
        r"^TGT_LANG\s*=\s*['\"][^'\"]*['\"]",
        f"TGT_LANG = '{tgt_lang}'",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if substituted == 0:
        raise RuntimeError("Could not locate TGT_LANG assignment in constants.py")
    CONSTANTS_FILE.write_text(new_text, encoding="utf-8")

class RunRequest(BaseModel):
    topic: str
    tgt_lang: str

class ScrapeRequest(BaseModel):
    topics: list[str]
    tgt_lang: str

class UpdateLangRequest(BaseModel):
    tgt_lang: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/jobs/scrape")
def start_scrape(req: ScrapeRequest):
    """Trigger scraping - runs main_scrape_bios.py scrape-bios"""
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id,
        "type": "scrape",
        "status": "queued",
        "payload": {"topics": req.topics, "tgt_lang": req.tgt_lang},
        "progress": 0,
        "error": None,
    }
    # Background worker runs the real scraper script
    def worker(job_id: str):
        JOBS[job_id]["status"] = "running"
        try:
            write_topics_file(req.topics)
            update_tgt_lang_constant(req.tgt_lang)

            logs_dir = Path(__file__).parent / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            log_path = logs_dir / f"{job_id}.log"
            JOBS[job_id]["log"] = str(log_path)

            python_exec = resolve_python_executable()

            cmd = [python_exec, "main_scrape_bios.py", "scrape-bios"]
            with open(log_path, "w", encoding="utf-8") as logf:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(BACKEND_DIR),
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                )
                try:
                    if proc.stdin:
                        proc.stdin.write(f"{req.tgt_lang}\n".encode("utf-8"))
                        proc.stdin.flush()
                        proc.stdin.close()
                except Exception:
                    pass

                while True:
                    ret = proc.poll()
                    if ret is not None:
                        if ret == 0:
                            JOBS[job_id]["status"] = "finished"
                            JOBS[job_id]["progress"] = 100
                        else:
                            JOBS[job_id]["status"] = "failed"
                            JOBS[job_id]["error"] = f"exit code {ret}"
                        break
                    time.sleep(1)
        except Exception as e:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(e)

    threading.Thread(target=worker, args=(job_id,), daemon=True).start()
    return {"id": job_id}

@app.post("/jobs/run")
def start_run(req: RunRequest):
    """Trigger InfoGap pipeline - runs main_complete_analysis.py run-multiple-topics"""
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id,
        "type": "run",
        "status": "queued",
        "payload": {"topic": req.topic, "tgt_lang": req.tgt_lang},
        "progress": 0,
        "error": None,
    }
    # Launch pipeline as a background subprocess
    def worker(job_id: str):
        JOBS[job_id]["status"] = "running"
        logs_dir = Path(__file__).parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / f"{job_id}.log"
        JOBS[job_id]["log"] = str(log_path)
        try:
            # Align constants with requested run
            update_tgt_lang_constant(req.tgt_lang)
            # Prefer the backend venv python if available
            python_exec = resolve_python_executable()

            env = os.environ.copy()
            env["TGT_LANG"] = req.tgt_lang

            # Command: run multiple topics pipeline (non-interactive)
            cmd = [python_exec, "main_complete_analysis.py", "run-multiple-topics"]

            with open(log_path, "w", encoding="utf-8") as logf:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(BACKEND_DIR),
                    env=env,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                )
                # Poll for status
                while True:
                    ret = proc.poll()
                    if ret is not None:
                        if ret == 0:
                            JOBS[job_id]["status"] = "finished"
                            JOBS[job_id]["progress"] = 100
                        else:
                            JOBS[job_id]["status"] = "failed"
                            JOBS[job_id]["error"] = f"exit code {ret}"
                            JOBS[job_id]["progress"] = JOBS[job_id].get("progress", 0)
                        break
                    time.sleep(1)
        except Exception as e:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(e)

    threading.Thread(target=worker, args=(job_id,), daemon=True).start()
    return {"id": job_id}

@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """Get job status"""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "id": job["id"],
        "status": job["status"],
        "progress": job.get("progress"),
        "error": job.get("error"),
        "log": job.get("log"),
    }

@app.get("/logs/{job_id}")
def get_logs(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    log_path = job.get("log")
    if not log_path or not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="log not found")
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        return {"log": f.read()}

@app.get("/results/{topic}")
def list_results(topic: str):
    if not SCRATCH_DIR:
        raise HTTPException(status_code=500, detail="SCRATCH_DIR not set")
    results_dir = Path(SCRATCH_DIR) / "ethics_annotation_save" / "wikigap_data"
    if not results_dir.exists():
        return {"topic": topic, "files": []}
    files = []
    for name in os.listdir(results_dir):
        if topic in name:
            files.append(str(results_dir / name))
    csv_dir = results_dir / "csv"
    if csv_dir.exists():
        for name in os.listdir(csv_dir):
            if topic in name:
                files.append(str(csv_dir / name))
    return {"topic": topic, "files": files}


@app.get("/results/{topic}/{tgt_lang}/csv")
def download_csv(topic: str, tgt_lang: str):
    if not SCRATCH_DIR:
        raise HTTPException(status_code=500, detail="SCRATCH_DIR not set")
    safe_topic = topic.replace(" ", "_")
    csv_path = Path(SCRATCH_DIR) / "ethics_annotation_save" / "wikigap_data" / "csv" / f"info_gap_{safe_topic}_{tgt_lang}.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="CSV not found")
    return FileResponse(csv_path, media_type="text/csv", filename=csv_path.name)


@app.post("/config/tgt-lang")
def set_tgt_lang(req: UpdateLangRequest):
    try:
        update_tgt_lang_constant(req.tgt_lang)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"tgt_lang": req.tgt_lang}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
