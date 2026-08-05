"""SQLite storage untuk Vimero Agent (tanpa ORM, cukup stdlib)."""
import json
import sqlite3
import threading
from datetime import datetime, timezone

from app.config import DATA_DIR, DB_PATH

_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    icon TEXT DEFAULT '🏢',
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    studio_id INTEGER REFERENCES studios(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    goal TEXT DEFAULT '',
    backstory TEXT DEFAULT '',
    model TEXT DEFAULT '',
    is_lead INTEGER DEFAULT 0,
    status TEXT DEFAULT 'aktif',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    agent_id INTEGER REFERENCES agents(id) ON DELETE SET NULL,
    instruction TEXT NOT NULL,
    expected_output TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER REFERENCES workflows(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'berjalan',
    input TEXT DEFAULT '',
    output TEXT DEFAULT '',
    model TEXT DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    agent_name TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'antre',
    output TEXT DEFAULT '',
    started_at TEXT,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER REFERENCES agents(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'antre',
    result TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    meta TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = get_conn()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
            if conn.execute("SELECT COUNT(*) c FROM studios").fetchone()["c"] == 0:
                _seed(conn)
        finally:
            conn.close()


# ---------------------------------------------------------------- seed data

SEED_STUDIOS = [
    ("Direksi", "direksi", "🏛️", "CEO & CTO — pengambil keputusan strategis."),
    ("Monitoring Data", "monitoring", "📊", "Pantau performa, trafik, dan penghasilan."),
    ("Studio Script", "studio-script", "✍️", "Riset hook, angle, dan penulisan script konten."),
    ("Studio Visual", "studio-visual", "🎨", "Produksi carousel, thumbnail, dan arahan visual."),
    ("Marketing", "marketing", "📣", "Strategi kampanye, distribusi, dan growth."),
    ("Affiliate AI", "affiliate", "🤝", "Riset produk affiliate dan konten promosi."),
    ("Customer Service", "customer-service", "💬", "Balas pertanyaan audiens dan follow-up leads."),
    ("Job Hunter", "job-hunter", "🎯", "Cari peluang project dan klien baru."),
]

SEED_AGENTS = [
    # (studio_slug, name, role, goal, backstory, is_lead)
    ("direksi", "Bimo", "CEO — Strategi Perusahaan",
     "Memastikan seluruh studio selaras dengan target bisnis dan revenue.",
     "Eksekutif berpengalaman di agensi kreatif digital, tegas tapi kolaboratif.", 1),
    ("direksi", "Raka", "CTO — Teknologi & Otomasi",
     "Mengotomasi alur kerja studio dan menjaga tooling AI tetap optimal.",
     "Engineer yang paham produksi konten dan integrasi AI.", 1),
    ("monitoring", "Adang", "Analis Monitoring",
     "Merangkum performa semua studio menjadi laporan yang tajam dan bisa dieksekusi.",
     "Analis data yang terobsesi dengan metrik retensi dan CTR.", 1),
    ("monitoring", "Akbar", "Analis Penghasilan",
     "Melacak revenue per kanal dan mencari peluang monetisasi baru.",
     "Mantan finance yang pindah ke dunia kreator ekonomi.", 0),
    ("studio-script", "Widi", "Kepala Studio Script",
     "Menjaga kualitas script: struktur jelas, hook kuat, CTA tepat.",
     "Scriptwriter senior untuk konten short-form yang viral.", 1),
    ("studio-script", "Nadia", "Marketing — Strategi Hook & Angle",
     "Menemukan hook dan angle paling relevan dengan target audiens.",
     "Peneliti tren sosial media, jago membaca komentar audiens.", 0),
    ("studio-visual", "Kirana", "Kepala Studio Visual",
     "Memastikan output visual konsisten dengan brand dan menarik perhatian dalam 1 detik.",
     "Art director dengan latar motion graphic.", 1),
    ("studio-visual", "Arif", "Produksi Carousel Konten",
     "Menyusun carousel edukatif yang enak dibaca dan mudah dibagikan.",
     "Desainer konten yang paham copywriting.", 0),
    ("studio-visual", "Rizky", "Thumbnail & Video AI",
     "Membuat konsep thumbnail dengan CTR tinggi.",
     "Spesialis thumbnail YouTube dan video AI.", 0),
    ("studio-visual", "Putri", "Thumbnail & Video AI",
     "Eksplorasi gaya visual baru untuk thumbnail dan video pendek.",
     "Ilustrator digital yang beralih ke AI tooling.", 0),
    ("studio-visual", "Salsa", "Thumbnail & Video AI",
     "Menguji varian thumbnail untuk A/B testing.",
     "Detail-oriented, suka eksperimen visual.", 0),
    ("marketing", "Mira", "Kepala Marketing",
     "Merancang kampanye dan strategi distribusi lintas kanal.",
     "Growth marketer dengan pengalaman brand lokal dan UMKM.", 1),
    ("affiliate", "Tari", "Kepala Affiliate AI",
     "Memilih produk affiliate berpotensi tinggi dan membuat konten promosinya.",
     "Affiliate marketer yang paham funnel dan copywriting.", 1),
    ("customer-service", "Sinta", "Kepala Customer Service",
     "Menjawab audiens dengan ramah dan mengubah pertanyaan menjadi konversi.",
     "CS berpengalaman di e-commerce.", 1),
    ("job-hunter", "Joni", "Kepala Job Hunter",
     "Menemukan peluang project/klien baru dan menyusun penawaran.",
     "Business development yang gigih dan rapi dalam riset prospek.", 1),
]

SEED_WORKFLOWS = [
    {
        "name": "Riset Produk",
        "slug": "riset-produk",
        "description": "Riset pasar → analisis kompetitor → sintesis insight & rekomendasi.",
        "steps": [
            ("Riset Pasar & Audiens", "Nadia",
             "Lakukan riset pasar untuk topik/produk berikut. Identifikasi target audiens, "
             "pain points, tren yang sedang naik, dan angle konten yang relevan.",
             "Ringkasan riset pasar dengan 5+ insight audiens."),
            ("Analisis Kompetitor", "Mira",
             "Berdasarkan riset pasar sebelumnya, analisis kompetitor utama: positioning, "
             "strategi konten, kelebihan/kelemahan, dan celah yang bisa dimanfaatkan.",
             "Tabel/daftar kompetitor + celah peluang."),
            ("Sintesis Insight & Rekomendasi", "Widi",
             "Gabungkan riset pasar dan analisis kompetitor menjadi rekomendasi strategi "
             "konten & marketing yang konkret dan bisa langsung dieksekusi minggu ini.",
             "Rekomendasi strategi dalam poin-poin prioritas."),
        ],
    },
    {
        "name": "Storyboard Video",
        "slug": "storyboard-video",
        "description": "Hook & angle → script → storyboard scene → arahan visual/thumbnail.",
        "steps": [
            ("Hook & Angle", "Nadia",
             "Buat 5 opsi hook (3 detik pertama) dan angle untuk video berdasarkan brief. "
             "Pilih 1 hook terbaik dan jelaskan alasannya.",
             "5 hook + 1 rekomendasi terbaik."),
            ("Penulisan Script", "Widi",
             "Tulis script video lengkap memakai hook terpilih: hook → isi (3 poin) → CTA. "
             "Gunakan bahasa percakapan yang natural.",
             "Script siap rekam dengan timestamp."),
            ("Storyboard Scene", "Kirana",
             "Pecah script menjadi storyboard per scene: visual, teks di layar, b-roll, durasi.",
             "Tabel storyboard per scene."),
            ("Arahan Visual & Thumbnail", "Rizky",
             "Buat 3 konsep thumbnail (komposisi, teks, ekspresi) + arahan warna/gaya "
             "yang konsisten dengan storyboard.",
             "3 konsep thumbnail + arahan visual."),
        ],
    },
    {
        "name": "Konten Carousel",
        "slug": "konten-carousel",
        "description": "Riset topik → copywriting per slide → arahan desain carousel.",
        "steps": [
            ("Riset Topik", "Nadia",
             "Riset topik carousel: apa yang paling dicari audiens, keyword, dan angle edukatif.",
             "Ringkasan riset + 3 opsi judul."),
            ("Copywriting Slide", "Arif",
             "Tulis copy carousel 7-10 slide: slide 1 hook kuat, isi ringkas per slide, "
             "slide akhir CTA.",
             "Copy lengkap per slide."),
            ("Arahan Desain", "Kirana",
             "Buat arahan desain carousel: layout per slide, hierarki teks, warna, dan gaya visual.",
             "Arahan desain siap eksekusi."),
        ],
    },
    {
        "name": "Laporan Harian",
        "slug": "laporan-harian",
        "description": "Rekap aktivitas semua studio menjadi laporan harian untuk direksi.",
        "steps": [
            ("Rekap & Analisis", "Adang",
             "Susun laporan harian: ringkasan aktivitas per studio, metrik penting, kendala, "
             "dan prioritas besok. Jika data terbatas, buat kerangka laporan yang bisa diisi.",
             "Laporan harian terstruktur."),
        ],
    },
]


def _seed(conn: sqlite3.Connection) -> None:
    ts = now()
    studio_ids = {}
    for name, slug, icon, desc in SEED_STUDIOS:
        cur = conn.execute(
            "INSERT INTO studios(name, slug, icon, description, created_at) VALUES(?,?,?,?,?)",
            (name, slug, icon, desc, ts),
        )
        studio_ids[slug] = cur.lastrowid
    agent_ids = {}
    for slug, name, role, goal, backstory, is_lead in SEED_AGENTS:
        cur = conn.execute(
            "INSERT INTO agents(studio_id, name, role, goal, backstory, is_lead, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (studio_ids[slug], name, role, goal, backstory, is_lead, ts),
        )
        agent_ids[name] = cur.lastrowid
    for wf in SEED_WORKFLOWS:
        cur = conn.execute(
            "INSERT INTO workflows(name, slug, description, created_at) VALUES(?,?,?,?)",
            (wf["name"], wf["slug"], wf["description"], ts),
        )
        wf_id = cur.lastrowid
        for pos, (title, agent_name, instruction, expected) in enumerate(wf["steps"], 1):
            conn.execute(
                "INSERT INTO workflow_steps(workflow_id, position, title, agent_id, "
                "instruction, expected_output) VALUES(?,?,?,?,?,?)",
                (wf_id, pos, title, agent_ids.get(agent_name), instruction, expected),
            )
    conn.commit()


# ---------------------------------------------------------------- helpers

def query(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        conn = get_conn()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> int:
    """Jalankan INSERT/UPDATE/DELETE, kembalikan lastrowid."""
    with _lock:
        conn = get_conn()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def all_settings() -> dict:
    return {r["key"]: r["value"] for r in query("SELECT key, value FROM settings")}


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings(key, value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def add_message(role: str, content: str, meta: dict | None = None) -> int:
    return execute(
        "INSERT INTO messages(role, content, meta, created_at) VALUES(?,?,?,?)",
        (role, content, json.dumps(meta or {}), now()),
    )
