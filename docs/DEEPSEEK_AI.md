# AI analyst on DeepSeek (v2.6)

From v2.6 the AI SOC analyst uses **DeepSeek** (api.deepseek.com). DeepSeek has an
OpenAI-compatible API, so the backend sends the same chat request as before, just to DeepSeek.
Without a key, or when DeepSeek can't be reached, the built-in offline analyst still answers.

## 1. Get the key

1. Open https://platform.deepseek.com and sign up (phone number or email).
2. **Top up** a small amount if the account shows no balance (DeepSeek is pay-as-you-go and cheap;
   a demo uses only a few cents).
3. **API keys** -> **Create new API key**, copy it (it starts with `sk-`). It is shown only once.

## 2. Put it in CyberShield

Dashboard: **Administration -> AI assistant**, paste the key, leave the model empty
(= `deepseek-chat`) and press **Save and test**. You should see `Working: deepseek answered ...`.

Or use `backend/.env` (for Docker, the `.env` next to `docker-compose.yml`):

```
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-key
DEEPSEEK_MODEL=deepseek-chat
```

Restart the backend after editing `.env`. A key saved in the dashboard wins over `.env`.

Models: `deepseek-chat` (fast, default) or `deepseek-reasoner` (thinks longer, slower).

## How it works

* `backend/app/ai_assistant.py`: provider `deepseek` -> `POST https://api.deepseek.com/chat/completions`
  with `Authorization: Bearer <key>`.
* The key is stored in the database (or `.env`) and never sent back to the browser (only its last 4 characters).
* Any error (no internet, wrong key, no balance) -> the offline analyst answers and the reply says why.
* The analyst still only **advises**. It suggests console commands; a human runs them.

## Other providers (still work from `.env`)

`AI_PROVIDER=huawei` (Huawei Cloud MaaS, v2.5, see `docs/HUAWEI_AI.md`), `gemini`, `groq`, `openrouter`, `omniroute`.

Not tested: a real DeepSeek key from this build environment. Tests check the request format with a fake
server (`backend/tests/test_v26.py`).
