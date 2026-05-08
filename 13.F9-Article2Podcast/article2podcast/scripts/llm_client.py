#!/usr/bin/env python3
"""
Unified LLM client — 直接调用 Bedrock / MiniMax，不依赖 litellm。

支持的 model 格式:
  - "bedrock/<model_id>"  → AWS Bedrock (boto3)
  - "minimax/<model_id>"  → MiniMax Anthropic 兼容 API (requests)

用法:
    from llm_client import llm_completion

    text = llm_completion(
        model="bedrock/us.anthropic.claude-opus-4-6-v1",
        prompt="你好",
        max_tokens=4000,
        temperature=0.8,
        config=config,          # config.json 内容
        credentials=credentials # credentials.json 内容（MiniMax 需要）
    )
"""

import json
import os


def _load_credentials() -> dict:
    """Load credentials.json from project root."""
    cred_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "credentials.json"
    )
    if os.path.exists(cred_path):
        with open(cred_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _call_bedrock(model_id: str, prompt: str, max_tokens: int,
                  temperature: float, region: str) -> str:
    """Call AWS Bedrock Converse/Messages API via boto3."""
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(read_timeout=600, connect_timeout=10),
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    })

    resp = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    resp_body = json.loads(resp["body"].read())

    # Extract text from content blocks
    text_parts = []
    for block in resp_body.get("content", []):
        if block.get("type") == "text":
            text_parts.append(block["text"])

    usage = resp_body.get("usage", {})
    in_tok = usage.get("input_tokens", 0)
    out_tok = usage.get("output_tokens", 0)
    print(f"   Bedrock tokens: in={in_tok} out={out_tok}", flush=True)

    return "".join(text_parts)


def _call_minimax(model_id: str, prompt: str, max_tokens: int,
                  temperature: float, credentials: dict,
                  config: dict) -> str:
    """Call MiniMax via Anthropic-compatible API."""
    import requests

    api_key = credentials.get("minimax_api_key", "")
    if not api_key:
        raise ValueError("minimax_api_key not found in credentials.json")

    # The Anthropic-compatible endpoint lives at a different path prefix
    # (/anthropic/v1/messages) than the TTS endpoint (/v1/...), and may
    # be served on a different host depending on the account region.  We
    # therefore keep a separate config key instead of reusing
    # minimax_api_base.
    api_base = config.get(
        "minimax_anthropic_api_base", "https://api.minimaxi.com"
    ).rstrip("/")
    url = f"{api_base}/anthropic/v1/messages"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    # MiniMax temperature range: (0.0, 1.0]
    temp = min(max(temperature, 0.01), 1.0)

    payload = {
        "model": model_id,
        "max_tokens": max_tokens,
        "temperature": temp,
        "messages": [{"role": "user", "content": prompt}],
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=300)
    resp.raise_for_status()
    data = resp.json()

    text_parts = []
    for block in data.get("content", []):
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))

    usage = data.get("usage", {})
    in_tok = usage.get("input_tokens", 0)
    out_tok = usage.get("output_tokens", 0)
    print(f"   MiniMax tokens: in={in_tok} out={out_tok}", flush=True)

    return "".join(text_parts)


def _call_one_model(model: str, prompt: str, max_tokens: int,
                     temperature: float, config: dict,
                     credentials: dict) -> str:
    """Dispatch a single call to the specified model.

    Raises on any backend failure so the caller can decide whether to
    fall through to a different model.
    """
    if model.startswith("bedrock/"):
        model_id = model[len("bedrock/"):]
        region = config.get("ai_model_region", "us-east-1")
        return _call_bedrock(model_id, prompt, max_tokens, temperature, region)

    if model.startswith("minimax/"):
        model_id = model[len("minimax/"):]
        return _call_minimax(model_id, prompt, max_tokens, temperature,
                             credentials, config)

    raise ValueError(
        f"Unsupported model format: '{model}'. "
        f"Use 'bedrock/<model_id>' or 'minimax/<model_id>'."
    )


def _resolve_fallback_models(config: dict, primary: str) -> list:
    """Return the fallback chain from config, excluding the primary.

    ``ai_model_fallback`` may be either a string or a list of strings.
    """
    raw = config.get("ai_model_fallback", [])
    if isinstance(raw, str):
        raw = [raw]
    return [m for m in raw if m and m != primary]


def llm_completion(model: str, prompt: str, max_tokens: int = 4000,
                   temperature: float = 0.8, config: dict = None,
                   credentials: dict = None) -> str:
    """统一 LLM 调用入口，支持主备降级。

    Args:
        model: 主模型。"bedrock/<model_id>" 或 "minimax/<model_id>"
        prompt: 用户 prompt 文本
        max_tokens: 最大输出 token 数（注意 MiniMax-M2 是 reasoning 模型，
            推理过程会消耗 tokens，预算要给得比正常 completion 大一些）
        temperature: 采样温度
        config: config.json 内容。可选 ``ai_model_fallback`` 字段
            （字符串或字符串列表），当主模型失败时依次尝试
        credentials: credentials.json 内容（MiniMax 需要 API key）

    Returns:
        LLM 生成的文本内容
    """
    config = config or {}
    credentials = credentials or _load_credentials()

    chain = [model] + _resolve_fallback_models(config, model)
    errors = []

    for idx, candidate in enumerate(chain):
        try:
            if idx > 0:
                print(f"   ↪ LLM 降级到 {candidate}", flush=True)
            return _call_one_model(candidate, prompt, max_tokens,
                                    temperature, config, credentials)
        except Exception as e:
            errors.append((candidate, e))
            # Keep the primary error concise in logs; surface the full
            # stack only if all candidates fail.
            print(f"   ⚠️ {candidate} 调用失败 ({type(e).__name__}: {e})",
                  flush=True)
            continue

    # All candidates exhausted
    summary = "; ".join(f"{m}: {type(e).__name__} {e}" for m, e in errors)
    raise RuntimeError(f"All LLM candidates failed: {summary}")
