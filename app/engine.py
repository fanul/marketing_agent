"""Mesin agentic Vimero: eksekusi agent, workflow pipeline, dan orchestrator.

Konsep (terinspirasi CrewAI): setiap "karyawan" adalah agent dengan persona
(role, goal, backstory). Workflow = pipeline task berurutan; output step
sebelumnya menjadi konteks step berikutnya. Orchestrator (Terminal Asisten)
memakai function-calling untuk mengelola perusahaan.
"""
import asyncio
import json

from app import db, llm
from app.config import get_settings

# referensi task background supaya tidak di-GC
_bg_tasks: set = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


# ---------------------------------------------------------------- persona

def agent_system_prompt(agent: dict) -> str:
    settings = get_settings()
    studio = ""
    if agent.get("studio_name"):
        studio = f"Kamu bagian dari {agent['studio_name']}."
    return (
        f"Kamu adalah {agent['name']}, {agent['role']} di {settings['company_name']}, "
        f"sebuah perusahaan marketing yang dijalankan tim AI. {studio}\n"
        f"Goal kamu: {agent.get('goal') or 'membantu perusahaan mencapai target.'}\n"
        f"Latar belakang: {agent.get('backstory') or '-'}\n\n"
        "Aturan kerja:\n"
        "- Jawab dalam Bahasa Indonesia yang natural dan profesional.\n"
        "- Langsung ke hasil kerja, jangan basa-basi.\n"
        "- Gunakan struktur (heading, poin, tabel markdown) agar mudah dibaca.\n"
        "- Kalau brief kurang jelas, buat asumsi wajar dan tulis asumsinya."
    )


def _get_agent(agent_id: int | None) -> dict | None:
    if not agent_id:
        return None
    return db.query_one(
        "SELECT a.*, s.name AS studio_name FROM agents a "
        "LEFT JOIN studios s ON s.id = a.studio_id WHERE a.id = ?",
        (agent_id,),
    )


async def run_agent(agent: dict, task_text: str, model: str | None = None) -> str:
    message = await llm.chat(
        [
            {"role": "system", "content": agent_system_prompt(agent)},
            {"role": "user", "content": task_text},
        ],
        model=model or agent.get("model") or None,
    )
    return message.get("content") or ""


# ---------------------------------------------------------------- workflow

async def execute_workflow(workflow_id: int, brief: str, model: str | None = None) -> int:
    """Buat run + jalankan pipeline di background. Kembalikan run_id."""
    wf = db.query_one("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
    if not wf:
        raise ValueError("Workflow tidak ditemukan")
    steps = db.query(
        "SELECT ws.*, a.name AS agent_name FROM workflow_steps ws "
        "LEFT JOIN agents a ON a.id = ws.agent_id "
        "WHERE ws.workflow_id = ? ORDER BY ws.position",
        (workflow_id,),
    )
    run_id = db.execute(
        "INSERT INTO runs(workflow_id, title, status, input, model, started_at) "
        "VALUES(?,?,?,?,?,?)",
        (workflow_id, wf["name"], "berjalan", brief, model or "", db.now()),
    )
    for step in steps:
        db.execute(
            "INSERT INTO run_steps(run_id, position, title, agent_name, status) "
            "VALUES(?,?,?,?,?)",
            (run_id, step["position"], step["title"], step["agent_name"] or "?", "antre"),
        )
    _spawn(_run_pipeline(run_id, steps, brief, model))
    return run_id


async def _run_pipeline(run_id: int, steps: list[dict], brief: str, model: str | None) -> None:
    context: list[tuple[str, str]] = []  # (judul step, output)
    final_output = ""
    try:
        for step in steps:
            rs = db.query_one(
                "SELECT id FROM run_steps WHERE run_id = ? AND position = ?",
                (run_id, step["position"]),
            )
            db.execute(
                "UPDATE run_steps SET status='berjalan', started_at=? WHERE id=?",
                (db.now(), rs["id"]),
            )
            agent = _get_agent(step["agent_id"]) or {
                "name": "Agent Umum", "role": "Generalis Marketing",
                "goal": "", "backstory": "",
            }
            prompt_parts = [f"## Brief dari klien/CEO\n{brief}\n"]
            if context:
                prompt_parts.append("## Hasil kerja rekan sebelumnya")
                for title, output in context:
                    prompt_parts.append(f"### {title}\n{output}\n")
            prompt_parts.append(f"## Tugas kamu sekarang: {step['title']}\n{step['instruction']}")
            if step.get("expected_output"):
                prompt_parts.append(f"\nOutput yang diharapkan: {step['expected_output']}")
            output = await run_agent(agent, "\n".join(prompt_parts), model=model)
            context.append((step["title"], output))
            final_output = output
            db.execute(
                "UPDATE run_steps SET status='selesai', output=?, finished_at=? WHERE id=?",
                (output, db.now(), rs["id"]),
            )
        db.execute(
            "UPDATE runs SET status='selesai', output=?, finished_at=? WHERE id=?",
            (final_output, db.now(), run_id),
        )
    except Exception as exc:  # simpan error agar terlihat di Ruang Laporan
        db.execute(
            "UPDATE runs SET status='gagal', output=?, finished_at=? WHERE id=?",
            (f"Error: {exc}", db.now(), run_id),
        )
        db.execute(
            "UPDATE run_steps SET status='gagal', output=? "
            "WHERE run_id=? AND status IN ('berjalan','antre')",
            (f"Error: {exc}", run_id),
        )


# ---------------------------------------------------------------- tugas tunggal

async def assign_task(agent_id: int, title: str, description: str,
                      model: str | None = None) -> int:
    task_id = db.execute(
        "INSERT INTO tasks(agent_id, title, description, status, created_at) "
        "VALUES(?,?,?,?,?)",
        (agent_id, title, description, "berjalan", db.now()),
    )
    _spawn(_run_task(task_id, agent_id, title, description, model))
    return task_id


async def _run_task(task_id: int, agent_id: int, title: str,
                    description: str, model: str | None) -> None:
    try:
        agent = _get_agent(agent_id)
        if not agent:
            raise ValueError("Karyawan tidak ditemukan")
        text = f"## Tugas: {title}\n{description or 'Kerjakan sebaik mungkin.'}"
        result = await run_agent(agent, text, model=model)
        db.execute(
            "UPDATE tasks SET status='selesai', result=?, finished_at=? WHERE id=?",
            (result, db.now(), task_id),
        )
    except Exception as exc:
        db.execute(
            "UPDATE tasks SET status='gagal', result=?, finished_at=? WHERE id=?",
            (f"Error: {exc}", db.now(), task_id),
        )


# ---------------------------------------------------------------- orchestrator

ORCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "karyawan",
            "description": "Lihat daftar semua karyawan (agent) per studio beserta perannya.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tambah_karyawan",
            "description": "Rekrut karyawan AI baru ke sebuah studio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama": {"type": "string"},
                    "peran": {"type": "string", "description": "Jabatan/peran, mis. 'Copywriter Iklan'"},
                    "studio_slug": {"type": "string", "description": "Slug studio tujuan"},
                    "goal": {"type": "string"},
                },
                "required": ["nama", "peran", "studio_slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tambah_studio",
            "description": "Buat studio/divisi baru.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama": {"type": "string"},
                    "deskripsi": {"type": "string"},
                },
                "required": ["nama"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "daftar_workflow",
            "description": "Lihat daftar workflow (alur kerja) yang tersedia beserta step-nya.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jalankan_workflow",
            "description": "Jalankan workflow dengan brief tertentu. Hasil muncul di Ruang Laporan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "brief": {"type": "string", "description": "Brief/topik untuk workflow"},
                },
                "required": ["slug", "brief"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tugaskan_karyawan",
            "description": "Berikan tugas tunggal langsung ke satu karyawan (by nama).",
            "parameters": {
                "type": "object",
                "properties": {
                    "nama": {"type": "string"},
                    "judul": {"type": "string"},
                    "deskripsi": {"type": "string"},
                },
                "required": ["nama", "judul"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "status_perusahaan",
            "description": "Ringkasan kondisi perusahaan: jumlah studio/karyawan, run & tugas terakhir.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


async def _tool_karyawan(_args: dict) -> dict:
    studios = db.query("SELECT * FROM studios ORDER BY id")
    agents = db.query("SELECT * FROM agents ORDER BY studio_id, is_lead DESC, id")
    out = {"jumlah_karyawan": len(agents), "per_studio": []}
    for s in studios:
        members = [a for a in agents if a["studio_id"] == s["id"]]
        lead = next((a["name"] for a in members if a["is_lead"]), None)
        out["per_studio"].append({
            "studio": s["name"], "slug": s["slug"], "kepala": lead,
            "tim": [{"nama": a["name"], "tugas": a["role"]} for a in members],
        })
    return out


async def _tool_tambah_karyawan(args: dict) -> dict:
    studio = db.query_one("SELECT * FROM studios WHERE slug = ?", (args["studio_slug"],))
    if not studio:
        return {"error": f"Studio '{args['studio_slug']}' tidak ada. "
                         "Gunakan tool karyawan untuk lihat slug yang valid."}
    agent_id = db.execute(
        "INSERT INTO agents(studio_id, name, role, goal, created_at) VALUES(?,?,?,?,?)",
        (studio["id"], args["nama"], args["peran"], args.get("goal", ""), db.now()),
    )
    return {"ok": True, "agent_id": agent_id,
            "pesan": f"{args['nama']} bergabung ke {studio['name']} sebagai {args['peran']}."}


async def _tool_tambah_studio(args: dict) -> dict:
    slug = args["nama"].lower().strip().replace(" ", "-")
    if db.query_one("SELECT id FROM studios WHERE slug = ?", (slug,)):
        return {"error": f"Studio '{slug}' sudah ada."}
    sid = db.execute(
        "INSERT INTO studios(name, slug, description, created_at) VALUES(?,?,?,?)",
        (args["nama"], slug, args.get("deskripsi", ""), db.now()),
    )
    return {"ok": True, "studio_id": sid, "slug": slug}


async def _tool_daftar_workflow(_args: dict) -> dict:
    wfs = db.query("SELECT * FROM workflows ORDER BY id")
    out = []
    for wf in wfs:
        steps = db.query(
            "SELECT ws.title, a.name AS agent FROM workflow_steps ws "
            "LEFT JOIN agents a ON a.id = ws.agent_id "
            "WHERE ws.workflow_id = ? ORDER BY ws.position",
            (wf["id"],),
        )
        out.append({"nama": wf["name"], "slug": wf["slug"],
                    "deskripsi": wf["description"],
                    "steps": [f"{s['title']} ({s['agent'] or '?'})" for s in steps]})
    return {"workflows": out}


async def _tool_jalankan_workflow(args: dict) -> dict:
    wf = db.query_one("SELECT * FROM workflows WHERE slug = ?", (args["slug"],))
    if not wf:
        return {"error": f"Workflow '{args['slug']}' tidak ditemukan."}
    run_id = await execute_workflow(wf["id"], args["brief"])
    return {"ok": True, "run_id": run_id,
            "pesan": f"Workflow '{wf['name']}' mulai dikerjakan tim. "
                     f"Pantau progresnya di Ruang Laporan (run #{run_id})."}


async def _tool_tugaskan_karyawan(args: dict) -> dict:
    agent = db.query_one(
        "SELECT * FROM agents WHERE lower(name) = lower(?)", (args["nama"],))
    if not agent:
        return {"error": f"Karyawan '{args['nama']}' tidak ditemukan."}
    task_id = await assign_task(agent["id"], args["judul"], args.get("deskripsi", ""))
    return {"ok": True, "task_id": task_id,
            "pesan": f"Tugas '{args['judul']}' diberikan ke {agent['name']}. "
                     f"Hasil muncul di Ruang Laporan (tugas #{task_id})."}


async def _tool_status(_args: dict) -> dict:
    return {
        "studio": db.query_one("SELECT COUNT(*) c FROM studios")["c"],
        "karyawan": db.query_one("SELECT COUNT(*) c FROM agents")["c"],
        "workflow": db.query_one("SELECT COUNT(*) c FROM workflows")["c"],
        "run_terakhir": db.query(
            "SELECT id, title, status, started_at FROM runs ORDER BY id DESC LIMIT 5"),
        "tugas_terakhir": db.query(
            "SELECT id, title, status FROM tasks ORDER BY id DESC LIMIT 5"),
    }


TOOL_IMPL = {
    "karyawan": _tool_karyawan,
    "tambah_karyawan": _tool_tambah_karyawan,
    "tambah_studio": _tool_tambah_studio,
    "daftar_workflow": _tool_daftar_workflow,
    "jalankan_workflow": _tool_jalankan_workflow,
    "tugaskan_karyawan": _tool_tugaskan_karyawan,
    "status_perusahaan": _tool_status,
}


def orchestrator_system_prompt() -> str:
    settings = get_settings()
    return (
        f"Kamu adalah Tomi, Terminal Asisten di {settings['company_name']} — perusahaan "
        "marketing yang seluruh karyawannya adalah agent AI. Kamu asisten utama bos "
        "(pengguna) untuk menjalankan perusahaan.\n\n"
        "Kemampuanmu lewat tools: lihat/rekrut karyawan, buat studio, lihat/jalankan "
        "workflow, beri tugas langsung, dan cek status perusahaan.\n\n"
        "Aturan:\n"
        "- Bahasa Indonesia santai-profesional (boleh 'lur', 'bos' seperlunya), tetap jelas.\n"
        "- Kalau butuh data (mis. siapa saja karyawan), SELALU panggil tool, jangan mengarang.\n"
        "- Untuk pekerjaan kreatif besar (riset produk, storyboard, carousel) arahkan ke "
        "jalankan_workflow; untuk tugas kecil spesifik gunakan tugaskan_karyawan.\n"
        "- Setelah menjalankan sesuatu, jelaskan singkat apa yang terjadi dan di mana "
        "hasilnya bisa dilihat.\n"
        "- Format jawaban dengan markdown."
    )


async def orchestrate(user_text: str, model: str | None = None,
                      history: list[dict] | None = None) -> dict:
    """Loop function-calling orchestrator. Mengembalikan
    {'content': str, 'tool_trace': [{name, args, result}]}"""
    messages: list[dict] = [{"role": "system", "content": orchestrator_system_prompt()}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user_text})
    trace: list[dict] = []

    for _ in range(6):
        try:
            msg = await llm.chat(messages, model=model, tools=ORCH_TOOLS)
        except llm.LLMError:
            if trace:
                raise
            # gateway mungkin tidak mendukung tools → fallback chat biasa
            msg = await llm.chat(messages, model=model)
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return {"content": msg.get("content") or "", "tool_trace": trace}
        messages.append(msg)
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            impl = TOOL_IMPL.get(name)
            result = (await impl(args)) if impl else {"error": f"Tool '{name}' tidak ada."}
            trace.append({"name": name, "args": args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": json.dumps(result, ensure_ascii=False),
            })
    return {"content": "Maaf, terlalu banyak langkah tool. Coba perintah yang lebih spesifik.",
            "tool_trace": trace}
