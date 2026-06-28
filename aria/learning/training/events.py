import time

TRAINING_TOPIC = "training"

def make_training_event(run_id, step, total_steps, status,
                        loss=None, preview_image=None) -> dict:
    """대시보드/WS가 소비하는 표준 학습 진행 이벤트.
    type='training'은 WS 메시지 라우팅 디스크리미네이터."""
    return {
        "type": TRAINING_TOPIC,
        "run_id": run_id,
        "step": step,
        "total_steps": total_steps,
        "status": status,            # "running" | "done" | "error"
        "metrics": {"loss": loss},
        "preview_image": preview_image,   # 대시보드가 표시할 경로/URL (없으면 None)
        "ts": time.time(),
    }
