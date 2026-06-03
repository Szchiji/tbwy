"""
AI Content Authenticity Scoring
Ported and adapted from fangzhang ai.py.
Calls Grok or TongYi Qwen-VL API to score image/video content quality.
Falls back to a default score when no API key is configured.
"""

import os
import json
import httpx

GROK_API_KEY = os.environ.get('GROK_API_KEY', '')
TONGYI_API_KEY = os.environ.get('TONGYI_API_KEY', '')

# Seconds before timing out AI API calls
AI_TIMEOUT = 30


def score_photo_authenticity(image_url: str) -> float:
    """
    Score content authenticity/quality. Returns a float 0-100.
    Higher score = higher quality / more likely authentic.

    Uses Grok Vision API if GROK_API_KEY is set,
    else TongYi Qwen-VL if TONGYI_API_KEY is set,
    otherwise returns a neutral default score of 75.
    """
    if not image_url:
        return 75.0

    if GROK_API_KEY:
        return _score_with_grok(image_url)
    if TONGYI_API_KEY:
        return _score_with_tongyi(image_url)

    # No API key configured — return default
    return 75.0


def _score_with_grok(image_url: str) -> float:
    """Call xAI Grok Vision API for content scoring."""
    prompt = (
        "请评估这张图片/视频截图的内容质量和真实性，给出 0-100 的评分。"
        "100 = 高质量真实原创内容，0 = 低质量/虚假/违规内容。"
        "只返回一个整数，不要其他文字。"
    )
    try:
        with httpx.Client(timeout=AI_TIMEOUT) as client:
            resp = client.post(
                'https://api.x.ai/v1/chat/completions',
                headers={
                    'Authorization': f'******',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': 'grok-vision-beta',
                    'messages': [
                        {
                            'role': 'user',
                            'content': [
                                {'type': 'image_url', 'image_url': {'url': image_url}},
                                {'type': 'text', 'text': prompt},
                            ],
                        }
                    ],
                    'max_tokens': 10,
                },
            )
        resp.raise_for_status()
        text = resp.json()['choices'][0]['message']['content'].strip()
        score = float(''.join(c for c in text if c.isdigit() or c == '.'))
        return max(0.0, min(100.0, score))
    except Exception as exc:
        print(f"[ai.py] Grok scoring error: {exc}")
        return 75.0


def _score_with_tongyi(image_url: str) -> float:
    """Call Alibaba TongYi Qwen-VL API for content scoring."""
    prompt = (
        "请评估这张图片的内容质量和真实性，给出 0-100 的评分。"
        "100 = 高质量真实原创内容，0 = 低质量/虚假/违规内容。"
        "只返回一个整数，不要其他文字。"
    )
    try:
        with httpx.Client(timeout=AI_TIMEOUT) as client:
            resp = client.post(
                'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation',
                headers={
                    'Authorization': f'******',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': 'qwen-vl-plus',
                    'input': {
                        'messages': [
                            {
                                'role': 'user',
                                'content': [
                                    {'image': image_url},
                                    {'text': prompt},
                                ],
                            }
                        ]
                    },
                },
            )
        resp.raise_for_status()
        text = resp.json()['output']['choices'][0]['message']['content'][0]['text'].strip()
        score = float(''.join(c for c in text if c.isdigit() or c == '.'))
        return max(0.0, min(100.0, score))
    except Exception as exc:
        print(f"[ai.py] TongYi scoring error: {exc}")
        return 75.0
