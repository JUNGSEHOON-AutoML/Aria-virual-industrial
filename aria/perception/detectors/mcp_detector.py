from __future__ import annotations


class MCPDetector:
    """MCP 도구를 Detector Protocol로 감싸는 어댑터.

    [base.py 불변식 준수]
    - applicability(): 무거운 추론 금지 — config 규칙만 본다(MCP 호출 금지).
    - run(): MCP 도구 호출 → 표준 result dict 매핑.
    - 수치 비교 불가 시 decision="n/a"(LLM 출력에서 pass/fail 파싱 금지).
    """

    def __init__(self, name, modality, server, tool,
                 applicability=None, result_map=None):
        self.name = name
        self.modality = modality
        self._server = server
        self._tool = tool
        self._appl = applicability or {}
        self._map = result_map or {}

    def applicability(self, image_meta: dict, product: dict | None) -> float:
        domains = self._appl.get("domains", [])
        if not domains or image_meta.get("domain") in domains:
            return float(self._appl.get("score", 0.4))
        return 0.05

    def run(self, image_path: str, product: dict | None) -> dict:
        from aria.mcp.mcp_client import get_mcp_client
        try:
            raw = get_mcp_client().call_tool(
                self._tool, {"image_path": image_path}, server_name=self._server)
        except Exception as e:
            return self._na(f"MCP 호출 실패: {e}")
        if isinstance(raw, dict) and raw.get("error"):
            return self._na(raw["error"])
        return self._to_standard(raw if isinstance(raw, dict) else {"text": str(raw)})

    def _to_standard(self, raw: dict) -> dict:
        g = lambda k, d=None: raw.get(self._map.get(k, k), d)
        score, threshold = g("score"), g("threshold")
        if isinstance(score, (int, float)) and isinstance(threshold, (int, float)):
            decision = "fail" if score > threshold else "pass"
        else:
            decision = "n/a"
        return {
            "score": score, "threshold": threshold, "decision": decision,
            "confidence": g("confidence", 0.5),
            "render_type": g("render_type", "none"),
            "overlay_path": g("overlay"),
            "regions": g("regions", []),
            "model_name": f"MCP:{self._server}.{self._tool}",
        }

    def _na(self, msg: str) -> dict:
        return {"score": None, "threshold": None, "decision": "n/a",
                "confidence": 0.0, "render_type": "none", "overlay_path": None,
                "regions": [], "model_name": f"MCP:{self._server}", "error": msg}
