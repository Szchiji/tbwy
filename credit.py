"""
星光值 (Credit) System
Six-tier reputation system ported and adapted from fangzhang credit.py.
"""

import json
from datetime import datetime

# 六境信用等级 (thresholds are inclusive lower bounds)
CREDIT_TIERS = [
    (500, '星际传说', '🌌'),
    (350, '超新星',   '🌟'),
    (200, '星云贤者', '💫'),
    (100, '星河旅人', '✨'),
    (50,  '银河游子', '🌙'),
    (0,   '星光萌新', '⭐'),
]

# Trigger definitions: event_type -> (delta, description)
CREDIT_EVENTS = {
    'post_approved':  (+15, '投稿被审核通过'),
    'post_liked':     (+1,  '投稿获得点赞'),
    'post_reported':  (-5,  '投稿被举报'),
    'comment_posted': (+1,  '发表了评论'),
}


def get_credit_tier(score: int) -> dict:
    """Return tier info dict for a given score."""
    for threshold, name, icon in CREDIT_TIERS:
        if score >= threshold:
            return {'name': name, 'icon': icon, 'min_score': threshold}
    return {'name': '星光萌新', 'icon': '⭐', 'min_score': 0}


def format_tier_badge(score: int) -> str:
    """Return a short badge string like '⭐ 星光萌新'."""
    tier = get_credit_tier(score)
    return f"{tier['icon']} {tier['name']}"


def next_tier_info(score: int) -> dict | None:
    """Return the next tier and how many points are needed, or None if max tier."""
    for threshold, name, icon in CREDIT_TIERS:
        if score < threshold:
            return {'name': name, 'icon': icon, 'min_score': threshold, 'needed': threshold - score}
    return None


def add_credit_event(conn, tg_id: str, event_type: str, extra_desc: str = '') -> int:
    """
    Apply a credit event to a user and return the new score.
    conn must be an active sqlite3 connection.
    """
    delta, desc = CREDIT_EVENTS.get(event_type, (0, event_type))
    if extra_desc:
        desc = f"{desc}: {extra_desc}"

    row = conn.execute(
        "SELECT credit_score, credit_history FROM users WHERE tg_id=?", (tg_id,)
    ).fetchone()
    if not row:
        return 100

    current = row['credit_score'] if row['credit_score'] is not None else 100
    new_score = max(0, current + delta)

    try:
        history = json.loads(row['credit_history'] or '[]')
    except (json.JSONDecodeError, TypeError):
        history = []

    history.append({
        'type': event_type,
        'delta': delta,
        'desc': desc,
        'score_after': new_score,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
    })
    # Keep only the last 50 events
    history = history[-50:]

    conn.execute(
        "UPDATE users SET credit_score=?, credit_history=? WHERE tg_id=?",
        (new_score, json.dumps(history, ensure_ascii=False), tg_id),
    )
    return new_score
