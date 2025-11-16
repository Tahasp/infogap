## WikiGap Frontend

**Local workflow:** Users clone the repo and run both frontend and local API server.

### Setup

```bash
npm install
```

### Run

```bash
npm run dev
```

Runs on `http://localhost:5173` and connects to local API at `http://localhost:8000`

### Full Local Workflow

1. Clone the repository
2. Set up backend: `.env` in `backend/` with `SCRATCH_DIR` and `THE_KEY`
3. Install backend deps: `cd backend && pip install -r requirements.txt`
4. Install API server deps: `cd backend_api && pip install -r requirements.txt`
5. **Start API server**: `cd backend_api && python server.py` (runs on port 8000)
6. **Start frontend**: `cd frontend && npm run dev` (runs on port 5173)
7. Open browser to `http://localhost:5173` and use the web UI

### Environment

- `VITE_API_URL` (default `http://localhost:8000`) - change if API runs on different port

