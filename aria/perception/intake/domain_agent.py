import os
from aria.core.config.vlm import get_vlm

_PROMPT = ("이 이미지는 산업 검사 데이터입니다. 어떤 제품/표면 종류인가요? "
           "(예: 금속표면·PCB·직물·캡슐·카펫 등) 한 단어 카테고리와 한 줄 근거만.")

def classify_domain(report: dict, k: int = 3) -> dict:
    imgs = report.get("images", [])[:k]
    if not imgs:
        return {"domain": "unknown", "rationale": "이미지 없음", "samples": 0}
    
    try:
        vlm = get_vlm()
    except Exception as e:
        return {"domain": "unknown", "rationale": f"VLM 공급자 로드 실패: {e}", "samples": 0}

    notes = []
    for p in imgs:
        try:
            res = vlm.analyze(p, _PROMPT)
            notes.append(res)
        except Exception as e:
            notes.append(f"VLM 실패: {e}")

    first = notes[0] if notes else ""
    domain = "unknown"
    if first and not (first.startswith("VLM") or "오류" in first or "실패" in first):
        words = first.split()
        if words:
            raw_word = "".join(c for c in words[0] if c.isalnum() or '\uac00' <= c <= '\ud7a3')
            domain = raw_word[:30] if raw_word else "unknown"

    return {"domain": domain, "rationale": first, "samples": len(imgs)}
