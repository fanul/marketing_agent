"""Vimero Agent — server FastAPI."""
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db, engine, llm
from app.config import STATIC_DIR, get_settings

app = FastAPI(title="Vimero Agent", version="1.0")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


# ---------------------------------------------------------------- schemas

class StudioIn(BaseModel):
    name: str
    icon: str = "🏢"
    description: str = ""


class AgentIn(BaseModel):
    name: str
    role: str
    goal: str = ""
    backstory: str = ""
    model: str = ""
    studio_id: int | None = None
    is_lead: bool = False


class StepIn(BaseModel):
    title: str
    agent_id: int | None = None
    instruction: str
    expected_output: str = ""


class WorkflowIn(BaseModel):
    name: str
    description: str = ""
    steps: list[StepIn] = Field(default_factory=list)


class RunIn(BaseModel):
    brief: str
    model: str = ""


class TaskIn(BaseModel):
    agent_id: int
    title: str
    description: str = ""
    model: str = ""


class ChatIn(BaseModel):
    text: str
    model: str = ""


class SettingsIn(BaseModel):
    api_base: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    models: str | None = None
    company_name: str | None = None


# ---------------------------------------------------------------- bootstrap

def _studios_with_agents() -> list[dict]:
    studios = db.query("SELECT * FROM studios ORDER BY id")
    agents = db.query("SELECT * FROM agents ORDER BY is_lead DESC, id")
    for s in studios:
        s["agents"] = [a for a in agents if a["studio_id"] == s["id"]]
        lead = next((a for a in s["agents"] if a["is_lead"]), None)
        s["lead_name"] = lead["name"] if lead else None
    return studios


def _workflows_with_steps() -> list[dict]:
    wfs = db.query("SELECT * FROM workflows ORDER BY id")
    for wf in wfs:
        wf["steps"] = db.query(
            "SELECT ws.*, a.name AS agent_name FROM workflow_steps ws "
            "LEFT JOIN agents a ON a.id = ws.agent_id "
            "WHERE ws.workflow_id = ? ORDER BY ws.position",
            (wf["id"],),
        )
    return wfs


@app.get("/api/bootstrap")
def bootstrap():
    settings = get_settings()
    return {
        "company_name": settings["company_name"],
        "default_model": settings["default_model"],
        "models": settings["model_list"],
        "api_key_set": bool(settings.get("api_key")),
        "studios": _studios_with_agents(),
        "workflows": _workflows_with_steps(),
    }


# ---------------------------------------------------------------- studios

@app.post("/api/studios")
def create_studio(body: StudioIn):
    slug = body.name.lower().strip().replace(" ", "-")
    if db.query_one("SELECT id FROM studios WHERE slug = ?", (slug,)):
        raise HTTPException(400, "Studio dengan nama itu sudah ada")
    sid = db.execute(
        "INSERT INTO studios(name, slug, icon, description, created_at) VALUES(?,?,?,?,?)",
        (body.name, slug, body.icon, body.description, db.now()),
    )
    return {"id": sid, "slug": slug}


@app.put("/api/studios/{studio_id}")
def update_studio(studio_id: int, body: StudioIn):
    db.execute(
        "UPDATE studios SET name=?, icon=?, description=? WHERE id=?",
        (body.name, body.icon, body.description, studio_id),
    )
    return {"ok": True}


@app.delete("/api/studios/{studio_id}")
def delete_studio(studio_id: int):
    db.execute("DELETE FROM studios WHERE id=?", (studio_id,))
    return {"ok": True}


# ---------------------------------------------------------------- agents

@app.post("/api/agents")
def create_agent(body: AgentIn):
    aid = db.execute(
        "INSERT INTO agents(studio_id, name, role, goal, backstory, model, is_lead, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (body.studio_id, body.name, body.role, body.goal, body.backstory,
         body.model, int(body.is_lead), db.now()),
    )
    return {"id": aid}


@app.put("/api/agents/{agent_id}")
def update_agent(agent_id: int, body: AgentIn):
    db.execute(
        "UPDATE agents SET studio_id=?, name=?, role=?, goal=?, backstory=?, model=?, "
        "is_lead=? WHERE id=?",
        (body.studio_id, body.name, body.role, body.goal, body.backstory,
         body.model, int(body.is_lead), agent_id),
    )
    return {"ok": True}


@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: int):
    db.execute("DELETE FROM agents WHERE id=?", (agent_id,))
    return {"ok": True}


# ---------------------------------------------------------------- workflows

@app.post("/api/workflows")
def create_workflow(body: WorkflowIn):
    slug = body.name.lower().strip().replace(" ", "-")
    if db.query_one("SELECT id FROM workflows WHERE slug = ?", (slug,)):
        raise HTTPException(400, "Workflow dengan nama itu sudah ada")
    wf_id = db.execute(
        "INSERT INTO workflows(name, slug, description, created_at) VALUES(?,?,?,?)",
        (body.name, slug, body.description, db.now()),
    )
    for pos, step in enumerate(body.steps, 1):
        db.execute(
            "INSERT INTO workflow_steps(workflow_id, position, title, agent_id, "
            "instruction, expected_output) VALUES(?,?,?,?,?,?)",
            (wf_id, pos, step.title, step.agent_id, step.instruction, step.expected_output),
        )
    return {"id": wf_id, "slug": slug}


@app.put("/api/workflows/{wf_id}")
def update_workflow(wf_id: int, body: WorkflowIn):
    if not db.query_one("SELECT id FROM workflows WHERE id = ?", (wf_id,)):
        raise HTTPException(404, "Workflow tidak ditemukan")
    db.execute(
        "UPDATE workflows SET name=?, description=? WHERE id=?",
        (body.name, body.description, wf_id),
    )
    db.execute("DELETE FROM workflow_steps WHERE workflow_id=?", (wf_id,))
    for pos, step in enumerate(body.steps, 1):
        db.execute(
            "INSERT INTO workflow_steps(workflow_id, position, title, agent_id, "
            "instruction, expected_output) VALUES(?,?,?,?,?,?)",
            (wf_id, pos, step.title, step.agent_id, step.instruction, step.expected_output),
        )
    return {"ok": True}


@app.delete("/api/workflows/{wf_id}")
def delete_workflow(wf_id: int):
    db.execute("DELETE FROM workflows WHERE id=?", (wf_id,))
    return {"ok": True}


@app.post("/api/workflows/{wf_id}/run")
async def run_workflow(wf_id: int, body: RunIn):
    try:
        run_id = await engine.execute_workflow(wf_id, body.brief, body.model or None)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"run_id": run_id}


# ---------------------------------------------------------------- runs & tasks

@app.get("/api/runs")
def list_runs():
    return db.query("SELECT * FROM runs ORDER BY id DESC LIMIT 100")


@app.get("/api/runs/{run_id}")
def get_run(run_id: int):
    run = db.query_one("SELECT * FROM runs WHERE id = ?", (run_id,))
    if not run:
        raise HTTPException(404, "Run tidak ditemukan")
    run["steps"] = db.query(
        "SELECT * FROM run_steps WHERE run_id = ? ORDER BY position", (run_id,))
    return run


@app.get("/api/tasks")
def list_tasks():
    return db.query(
        "SELECT t.*, a.name AS agent_name FROM tasks t "
        "LEFT JOIN agents a ON a.id = t.agent_id ORDER BY t.id DESC LIMIT 100")


@app.post("/api/tasks")
async def create_task(body: TaskIn):
    if not db.query_one("SELECT id FROM agents WHERE id = ?", (body.agent_id,)):
        raise HTTPException(404, "Karyawan tidak ditemukan")
    task_id = await engine.assign_task(
        body.agent_id, body.title, body.description, body.model or None)
    return {"task_id": task_id}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: int):
    task = db.query_one(
        "SELECT t.*, a.name AS agent_name FROM tasks t "
        "LEFT JOIN agents a ON a.id = t.agent_id WHERE t.id = ?", (task_id,))
    if not task:
        raise HTTPException(404, "Tugas tidak ditemukan")
    return task


# ---------------------------------------------------------------- chat

@app.get("/api/messages")
def list_messages():
    msgs = db.query("SELECT * FROM messages ORDER BY id DESC LIMIT 50")
    msgs.reverse()
    for m in msgs:
        m["meta"] = json.loads(m["meta"] or "{}")
    return msgs


@app.post("/api/chat")
async def chat(body: ChatIn):
    settings = get_settings()
    if not settings.get("api_key"):
        raise HTTPException(
            400,
            "API key belum diatur. Buka Pengaturan lalu isi API key gateway "
            "(adaCODE/OpenRouter), atau set VIMERO_API_KEY di file .env.",
        )
    db.add_message("user", body.text)
    # pakai 10 pesan terakhir sebagai konteks percakapan
    history = []
    for m in db.query(
        "SELECT role, content FROM messages ORDER BY id DESC LIMIT 11")[::-1][:-1]:
        if m["role"] in ("user", "assistant") and m["content"]:
            history.append({"role": m["role"], "content": m["content"]})
    try:
        result = await engine.orchestrate(
            body.text, model=body.model or None, history=history[-10:])
    except llm.LLMError as exc:
        raise HTTPException(502, str(exc))
    db.add_message("assistant", result["content"],
                   {"tool_trace": result["tool_trace"], "model": body.model or settings["default_model"]})
    return result


@app.delete("/api/messages")
def clear_messages():
    db.execute("DELETE FROM messages")
    return {"ok": True}


# ---------------------------------------------------------------- settings

@app.get("/api/settings")
def read_settings():
    s = get_settings()
    key = s.get("api_key", "")
    return {
        "api_base": s["api_base"],
        "api_key_masked": (key[:6] + "…" + key[-4:]) if len(key) > 12 else ("(terisi)" if key else ""),
        "default_model": s["default_model"],
        "models": s["models"],
        "company_name": s["company_name"],
    }


@app.put("/api/settings")
def write_settings(body: SettingsIn):
    for key, value in body.model_dump(exclude_none=True).items():
        db.set_setting(key, value)
    return {"ok": True}


# ---------------------------------------------------------------- static

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
