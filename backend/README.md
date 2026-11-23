# Backend (FastAPI)

```bash
python -m venv venv
# Windows: venv\Scripts\Activate.ps1   macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

* API docs: http://127.0.0.1:8000/docs
* Health: `GET /api/health`
* Info: `GET /api/info`
* Live channel: WebSocket `/ws` (messages are `{"type": ..., "data": ...}`)
