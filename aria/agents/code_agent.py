"""CodeAgent — 코드 생성 + 수학적 증명 서브 에이전트.
Phase 3: 파이프라인 코드 동적 생성
Phase 4: 알고리즘 수학적/논리적 증명 문서 작성"""

import json
import os
import urllib.request

from aria.agents.base_agent import BaseAgent

_OLLAMA_BASE = os.environ.get("OLLAMA_API_BASE", "http://172.17.0.1:11434")
OLLAMA_API = f"{_OLLAMA_BASE}/api/chat"
OUTPUT_DIR = "outputs"


class CodeAgent(BaseAgent):
    name = "code"
    description = "코드 생성, 파이프라인 구축, 수학적 증명, 디버깅"

    # ──────────────────────────────────────────────────────────────────
    # build_pipeline(): GAP 4 — 추론 코드 + 수학적 증명 생성
    # ──────────────────────────────────────────────────────────────────
    def build_pipeline(self, selected_model: dict, analysis: dict) -> dict:
        """
        선택된 모델의 추론 코드와 수학적 증명을 생성.

        Args:
            selected_model: {"model": "ccifps", "source": "...", "reason": "..."}
            analysis: VLM 분석 결과 dict

        Returns:
            {"generated_code_path": "...", "proof_path": "...", "proof_summary": "..."}
        """
        model_name = selected_model.get("model", "unknown")
        source = selected_model.get("source", "unknown")
        reason = selected_model.get("reason", "")
        task = analysis.get("task", "object_detection")
        domain = analysis.get("domain", "unknown")

        print(f"[CodeAgent] 🛠️ 파이프라인 코드 생성 시작: {model_name}")

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # ── Step 1: 추론 코드 생성 (최대 2회 시도) ──
        code_path = os.path.join(OUTPUT_DIR, "inference_pipeline.py")
        code_content = self._generate_code(
            model_name, source, task, domain, max_retries=2)

        if code_content:
            with open(code_path, "w", encoding="utf-8") as f:
                f.write(code_content)
            print(f"[CodeAgent] ✅ 코드 저장: {code_path}")
        else:
            code_path = None
            print("[CodeAgent] ⚠️ 코드 생성 실패 (2회 시도)")

        # ── Step 2: 수학적 증명 생성 ──
        proof_path = os.path.join(OUTPUT_DIR, "algorithm_proof.md")
        proof_summary = self._generate_proof(
            model_name, source, reason, task, domain)

        if proof_summary:
            with open(proof_path, "w", encoding="utf-8") as f:
                f.write(proof_summary)
            print(f"[CodeAgent] ✅ 증명 저장: {proof_path}")
        else:
            proof_path = None
            proof_summary = "증명 생성 실패."

        # 요약 추출 (텔레그램 표시용, 300자)
        summary_short = proof_summary[:300] if proof_summary else ""

        return {
            "generated_code_path": code_path,
            "proof_path": proof_path,
            "proof_summary": summary_short,
        }

    def _generate_code(self, model_name: str, source: str,
                       task: str, domain: str,
                       max_retries: int = 2) -> str:
        """추론 파이프라인 코드 생성. Doom Loop 방지: 최대 2회."""

        prompt = f"""너는 엣지 환경(VRAM 4GB 이하) Python 엔지니어야.
아래 모델을 사용해서 이미지를 추론하는 코드를 작성해.

모델: {model_name}
소스: {source}
태스크: {task}
도메인: {domain}

요구사항:
1. 이미지 경로를 인자로 받아 추론 결과를 반환하는 함수
2. GPU/CPU 자동 감지
3. 메모리 효율적 (torch.no_grad() 사용)
4. 결과를 JSON으로 반환

Python 코드만 출력해. 설명 없이. ```python 태그 없이."""

        for attempt in range(max_retries):
            try:
                response = self._call_llm(prompt, timeout=60)
                if response and "def " in response and "import " in response:
                    # 코드 정리
                    if "```python" in response:
                        response = response.split("```python")[-1]
                        response = response.split("```")[0]
                    return response.strip()
                print(f"[CodeAgent] 코드 생성 시도 {attempt+1}/{max_retries}: 유효하지 않은 출력")
            except Exception as e:
                print(f"[CodeAgent] 코드 생성 시도 {attempt+1}/{max_retries} 실패: {e}")

        return None

    def _generate_proof(self, model_name: str, source: str,
                        reason: str, task: str, domain: str) -> str:
        """알고리즘 수학적 증명 문서 생성."""

        prompt = f"""너는 컴퓨터비전 공학 박사야.
아래 알고리즘이 엣지 환경(VRAM 4GB 이하, 제한된 연산)에서
왜 효율적이고 안정적인지 수학적으로 증명해.

알고리즘: {model_name}
용도: {task} ({domain})
선택 이유: {reason}

반드시 아래 항목을 포함해:
1. **시간 복잡도 (Time Complexity)**: O(?) 표기와 도출 과정
2. **VRAM 사용량 추정**: 구체적 수식 (예: 패치수 × 특성차원 × 바이트)
3. **차원 축소 논리**: PCA/임베딩 등 왜 고차원 → 저차원이 가능한지
4. **파라미터-프리 특성**: 학습 없이 추론이 가능한 구조적 이유
5. **결론**: 엣지 환경 적합성 최종 판단

마크다운 형식으로, 한국어로 작성해. 수식은 LaTeX 표기."""

        try:
            response = self._call_llm(prompt, timeout=90)
            if response:
                # 헤더 추가
                header = (
                    f"# 알고리즘 수학적 증명: {model_name}\n\n"
                    f"- 태스크: {task}\n"
                    f"- 도메인: {domain}\n"
                    f"- 선택 이유: {reason[:100]}\n\n---\n\n"
                )
                return header + response
        except Exception as e:
            print(f"[CodeAgent] 증명 생성 실패: {e}")

        return None

    def _call_llm(self, prompt: str, timeout: int = 60) -> str:
        """deepseek-r1 호출 (공통)."""
        payload = json.dumps({
            "model": "deepseek-r1:8b",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.0, "num_ctx": 4096},
        }).encode()

        req = urllib.request.Request(
            OLLAMA_API, data=payload,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())

        response = data["message"]["content"].strip()
        if "</think>" in response:
            response = response.split("</think>")[-1].strip()
        return response

    def apply_improvement_draft(self) -> dict:
        """
        outputs/improvement_draft.md 의 제안 사안에 따라
        app.py 등 소스코드의 파라미터(THRESHOLD 등)를 자율 수정(Rewrite)합니다.
        """
        import os
        import re
        from pathlib import Path
        
        base_dir = Path(__file__).parent.parent.resolve()
        draft_path = base_dir / "outputs" / "improvement_draft.md"
        app_path = base_dir / "app.py"
        
        if not draft_path.exists():
            return {"status": "error", "summary": "개선안 초안(improvement_draft.md)이 존재하지 않습니다."}
            
        draft_content = draft_path.read_text(encoding="utf-8")
        
        # 1. THRESHOLD 값 추출 시도
        threshold_match = re.search(r"THRESHOLD\s*=\s*([\d\.]+)", draft_content, re.IGNORECASE)
        if not threshold_match:
            # LLM을 통해 improvement_draft.md에서 THRESHOLD 최적화 값을 추출
            prompt = f"""아래 개선안 문서에서 제안하는 최적의 THRESHOLD 변수 값을 숫자 하나로만 추출해줘.
예를 들어 THRESHOLD = 16.5를 제안한다면 16.5만 출력해야 해. 다른 설명은 절대 금지.
            
=== 개선안 문서 ===
{draft_content}
"""
            try:
                llm_res = self._call_llm(prompt, timeout=30).strip()
                threshold_match = re.search(r"([\d\.]+)", llm_res)
            except Exception:
                pass

        if threshold_match:
            new_threshold = float(threshold_match.group(1))
            print(f"[CodeAgent] 개선안에서 추출된 최적 THRESHOLD: {new_threshold}")
            
            # 2. app.py 수정
            if app_path.exists():
                app_content = app_path.read_text(encoding="utf-8")
                # THRESHOLD = 15.0 등의 라인 찾아서 변경
                updated_content, count = re.subn(r"(THRESHOLD\s*=\s*)([\d\.]+)", f"\\1{new_threshold}", app_content)
                if count > 0:
                    app_path.write_text(updated_content, encoding="utf-8")
                    msg = f"app.py의 THRESHOLD를 {new_threshold}로 성공적으로 업데이트했습니다."
                    print(f"[CodeAgent] {msg}")
                    return {"status": "success", "summary": msg, "new_threshold": new_threshold}
                else:
                    return {"status": "error", "summary": "app.py 내에서 THRESHOLD 변수를 찾을 수 없습니다."}
            else:
                return {"status": "error", "summary": "app.py 파일을 찾을 수 없습니다."}
        else:
            return {"status": "error", "summary": "개선안 문서에서 수정할 THRESHOLD 값을 추출하지 못했습니다."}

    # ──────────────────────────────────────────────────────────────────
    # run(): 기존 인터페이스 유지 (대화형 호출용)
    # ──────────────────────────────────────────────────────────────────
    def run(self, user_input, image_path=None, context=None):
        ctx_str = ""
        if context:
            for k, v in context.items():
                if isinstance(v, dict) and v.get("summary"):
                    ctx_str += f"\n[{k}] {v['summary'][:200]}"

        prompt = f"""너는 숙련된 Python 프로그래머야.
사용자 요청에 대해 코드로 답해줘.
{f'참고 컨텍스트: {ctx_str}' if ctx_str else ''}

사용자: {user_input}

코드와 설명을 한국어로 답해."""

        try:
            response = self._call_llm(prompt, timeout=120)
            return {
                "status": "success",
                "summary": response[:500],
            }
        except Exception as e:
            return {"status": "error", "summary": f"코드 에이전트 오류: {e}"}

