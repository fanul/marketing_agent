# Vimero Agent 🏢🤖

**Agentic AI yang menjalankan perusahaan marketing** — seluruh "karyawan" adalah agent AI
yang bisa direkrut, diorganisir ke dalam studio, dan dipekerjakan lewat workflow atau
perintah langsung dari terminal.

Terinspirasi oleh [CrewAI-Studio](https://github.com/strnad/CrewAI-Studio)
(konsep agent → crew → task → run), di-improve dengan:

- **Terminal Asisten (orchestrator)** — chat dengan *Tomi*, asisten yang punya *function
  calling* untuk mengelola perusahaan: lihat/rekrut karyawan, buat studio, jalankan
  workflow, beri tugas, cek status. Tool trace-nya terlihat di terminal.
- **Workflow pipeline antar-agent** — output step sebelumnya otomatis jadi konteks step
  berikutnya (riset → analisis → sintesis). Workflow bisa dibuat/diedit dari UI.
- **Struktur perusahaan fleksibel** — studio (divisi) dan karyawan (agent dengan persona:
  peran, goal, backstory, model khusus) bisa ditambah kapan saja, dari UI maupun lewat
  perintah chat.
- **Ruang Laporan** — semua hasil kerja (workflow run per step + tugas individu)
  tersimpan dan auto-refresh selama pekerjaan berjalan.
- **Gateway-agnostic** — semua endpoint OpenAI-compatible didukung (adaCODE, OpenRouter,
  dll); model bisa diganti per-percakapan, per-agent, atau default.

## Struktur bawaan (bisa diubah semua)

| Studio | Kepala | Tim |
|---|---|---|
| Direksi | Bimo (CEO), Raka (CTO) | — |
| Monitoring Data | Adang | Akbar (Penghasilan) |
| Studio Script | Widi | Nadia (Hook & Angle) |
| Studio Visual | Kirana | Arif, Rizky, Putri, Salsa |
| Marketing | Mira | — |
| Affiliate AI | Tari | — |
| Customer Service | Sinta | — |
| Job Hunter | Joni | — |

Workflow bawaan: **Riset Produk**, **Storyboard Video**, **Konten Carousel**, **Laporan Harian**.

## Menjalankan

```bash
pip install -r requirements.txt
copy .env.example .env   # lalu isi VIMERO_API_KEY
python run.py
```

Buka `http://127.0.0.1:8021`. API key juga bisa diisi belakangan lewat menu **Pengaturan**.

## Contoh perintah di Terminal Asisten

- `siapa saja karyawan kita malam ini?`
- `jalankan riset produk untuk skincare lokal Gen Z`
- `buatkan storyboard video tentang tips AI untuk UMKM`
- `rekrut copywriter iklan bernama Dina di studio script`
- `tugaskan Rizky bikin 5 konsep thumbnail untuk video "AI ganti kerjaan?"`

## Arsitektur

```
run.py                 → uvicorn entry
app/config.py          → env + settings (DB override)
app/db.py              → SQLite (studios, agents, workflows, runs, tasks, messages) + seed
app/llm.py             → klien gateway OpenAI-compatible (chat, stream, tools)
app/engine.py          → eksekusi agent, pipeline workflow, orchestrator function-calling
app/main.py            → FastAPI REST API + static
static/                → UI terminal-style (vanilla JS, tanpa build step)
data/vimero.db         → dibuat otomatis saat pertama jalan
```
