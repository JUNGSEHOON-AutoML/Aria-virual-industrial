import time, math
from aria.learning.training.events import make_training_event

def run_dummy_training(run_id: str, manifest: dict, publish, n_steps: int = 20,
                       step_delay: float = 0.4) -> None:
    """가짜 학습 — 주입된 publish(event)로만 외부와 통신(웹/버스 의존 없음).
    preview는 업로드 이미지를 순환시켜 '움직이는 장면' 느낌을 준다."""
    imgs = manifest.get("images", []) or [None]
    try:
        for step in range(1, n_steps + 1):
            loss = round(2.0 * math.exp(-3.0 * step / n_steps) + 0.05, 4)  # 감소 곡선
            preview = imgs[step % len(imgs)]
            # 윈도우 경로를 웹 URL로 사용할 수 있도록 변환해야 할 수도 있지만, 일단 파일 경로를 그대로 전송.
            # 웹서버에서 해당 경로를 서비스하도록 하거나, 클라이언트쪽에서 처리해야 함.
            publish(make_training_event(run_id, step, n_steps, "running",
                                        loss=loss, preview_image=preview))
            time.sleep(step_delay)
        publish(make_training_event(run_id, n_steps, n_steps, "done", loss=loss,
                                    preview_image=imgs[-1]))
    except Exception as e:
        publish(make_training_event(run_id, 0, n_steps, "error"))
        raise
