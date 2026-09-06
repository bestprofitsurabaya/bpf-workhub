# Komunikasi dengan Ox Alpha — BPF WorkHub

## Ringkasan

Ox Alpha (`stealth/ox-alpha`) adalah model LLM yang tersedia via **OpenRouter API**. Bisa diakses langsung dari server ini tanpa perlu install apapun.

---

## Konfigurasi

| Parameter | Value |
|-----------|-------|
| **API Endpoint** | `https://openrouter.ai/api/v1/chat/completions` |
| **Model** | `stealth/ox-alpha` |
| **API Key** | Environment variable: `$OPENROUTER_API_KEY` |
| **Base URL (Anthropic-style)** | `https://openrouter.ai/api` |
| **Cost** | Gratis (free tier) |

---

## Cara Komunikasi via cURL

### Dasar — Kirim Pesan & Dapat Respons

```bash
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "stealth/ox-alpha",
    "messages": [
      {"role": "user", "content": "Pesan kamu di sini"}
    ],
    "max_tokens": 500
  }' | python3 -m json.tool
```

### Multi-Turn Conversation (Chat History)

```bash
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "stealth/ox-alpha",
    "messages": [
      {"role": "system", "content": "Kamu adalah asisten coding yang membantu proyek BPF WorkHub."},
      {"role": "user", "content": "Jelaskan arsitektur project ini"},
      {"role": "assistant", "content": "Arsitektur project ini..."},
      {"role": "user", "content": "Bagian mana yang perlu dioptimasi?"}
    ],
    "max_tokens": 1000
  }' | python3 -m json.tool
```

### Request dengan Reasoning (Chain of Thought)

```bash
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "stealth/ox-alpha",
    "messages": [
      {"role": "user", "content": "Analisis kode ini dan cari bug潜在"}
    ],
    "max_tokens": 2000
  }' | python3 -m json.tool
```

### Streaming Response

```bash
curl -s -N https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "stealth/ox-alpha",
    "messages": [
      {"role": "user", "content": "Tulis function Python untuk validasi email"}
    ],
    "max_tokens": 500,
    "stream": true
  }'
```

---

## Contoh Penggunaan Praktis

### 1. Code Review

```bash
CODE=$(cat app.py | head -50)

curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"stealth/ox-alpha\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Review kode ini, cari bug dan beri saran perbaikan:\n\n$CODE\"}
    ],
    \"max_tokens\": 1500
  }" | python3 -c "import sys,json; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

### 2. Generate Kode

```bash
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "stealth/ox-alpha",
    "messages": [
      {"role": "user", "content": "Tulis Python function untuk generate laporan PDF dari data penjualan. Gunakan library reportlab."}
    ],
    "max_tokens": 2000
  }' | python3 -c "import sys,json; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

### 3. Debug Error

```bash
ERROR_MSG="KeyError: 'user_id' di line 42"

curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"stealth/ox-alpha\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Saya dapat error ini: $ERROR_MSG. Ini di Flask app dengan SQLAlchemy. Bagaimana cara fix?\"}
    ],
    \"max_tokens\": 1000
  }" | python3 -c "import sys,json; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

---

## Environment Variables

Pastikan variabel berikut tersedia di shell:

```bash
# Sudah terkonfigurasi di server ini:
OPENROUTER_API_KEY=sk-or-v1-7fb5...
ANTHROPIC_BASE_URL=https://openrouter.ai/api
ANTHROPIC_DEFAULT_SONNET_MODEL=stealth/ox-alpha
```

Untuk cek:
```bash
echo $OPENROUTER_API_KEY
```

---

## Catatan Penting

- **Model**: `stealth/ox-alpha` (via OpenRouter, provider: Stealth)
- **Cost**: Gratis (cost: 0)
- **Max tokens**: Bisa diatur, default biasanya 4096
- **Reasoning**: Model ini mendukung reasoning/chain-of-thought (muncul di field `reasoning` pada response)
- **API format**: Kompatibel dengan OpenAI Chat Completions API format
- **Tidak perlu install**: Cukup pakai `curl` yang sudah ada di server

---

## Troubleshooting

| Masalah | Solusi |
|---------|--------|
| `curl: (6) Could not resolve host` | Cek koneksi internet server |
| `401 Unauthorized` | Cek API key: `echo $OPENROUTER_API_KEY` |
| `429 Too Many Requests` | Tunggu beberapa detik, lalu coba lagi |
| `Model not found` | Pastikan model: `stealth/ox-alpha` |
| Response kosong | Cek field `choices[0].message.content` di JSON |

---

*Terakhir diperbarui: 25 Agustus 2026*
*Dibuat oleh: Codebuff 🤖*
