# AI analyst on Huawei Cloud (v2.5)

> **v2.6:** the default AI analyst is now **DeepSeek** (`docs/DEEPSEEK_AI.md`). This Huawei MaaS
> option still works with `AI_PROVIDER=huawei` in `.env`.

From v2.5 the AI SOC analyst runs on **Huawei Cloud ModelArts Studio (MaaS)**, Huawei's
model service. It has an OpenAI-compatible API, so the backend just points to it. Without a
key, the built-in offline analyst still answers.

## 1. Get the key (Huawei Cloud console)

1. Log in at console-intl.huaweicloud.com and pick the region **AP-Singapore**.
2. Open **ModelArts Studio (MaaS)** -> **Model Inference** (Real-Time Inference) and enable a
   ready model such as DeepSeek-V3 or Qwen3 (free trial tokens are available).
3. **API Keys** -> **Create API Key** and copy it.
4. Open the model's **View Call Description**. Copy the **API address** and the **model name**.

## 2. Put it in CyberShield

Dashboard: **Administration -> AI assistant**, fill in the API address, model and API key, then
press **Save and test**. Or use `.env`:

```
AI_PROVIDER=huawei
AI_API_KEY=your-maas-api-key
HUAWEI_MAAS_URL=https://api-ap-southeast-1.modelarts-maas.com/v1
HUAWEI_MAAS_MODEL=DeepSeek-V3
```

Use the model name exactly as the console shows it.

## Huawei technology map

| Part of CyberShield | Huawei technology |
|---|---|
| Hosting (backend + dashboard) | Huawei Cloud **ECS** (Docker), optional **ELB** for HTTPS |
| Database | Huawei Cloud **RDS for PostgreSQL** |
| Device connection | Huawei Cloud **IoTDA** (MQTTS 8883) |
| AI SOC analyst | **DeepSeek** API (v2.6); Huawei MaaS still optional |
| Anomaly detection model | **ModelArts** training with **MindSpore** |
| Monitoring | Huawei Cloud **AOM** reading `/metrics` |
| Design | Huawei Cloud console / SecMaster layout, colors from Huawei's **DevUI** design system |

Optional parts that still use other services: phone alarm (ntfy/Telegram) and threat intel
feeds (VirusTotal/AbuseIPDB/OTX). Both are off by default.

CyberShield SecOps is a student project *built on* Huawei Cloud. It is not a Huawei product,
so it uses no Huawei logo.

Not tested: a real MaaS key from this build environment. The API format follows the Huawei
Cloud MaaS docs (Bearer key, `/v1/chat/completions`).
