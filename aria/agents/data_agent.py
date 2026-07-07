"""DataAgent — 데이터 분석 서브 에이전트.
CSV/Excel 분석, 통계 요약, 차트 생성, Kaggle 연동."""

import json
import os
import urllib.request

from aria.agents.base_agent import BaseAgent

_OLLAMA_BASE = os.environ.get("OLLAMA_API_BASE", "http://172.17.0.1:11434")
OLLAMA_API = f"{_OLLAMA_BASE}/api/chat"
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "outputs")


class DataAgent(BaseAgent):
    name = "data"
    description = "CSV, Excel, 데이터 분석, 차트, 통계, Kaggle"

    def run(self, user_input, image_path=None, context=None):
        lower = user_input.lower()

        # Kaggle 검색
        if "kaggle" in lower:
            return self._kaggle_search(user_input)

        # 파일 분석 (경로가 주어진 경우)
        file_path = self._extract_file_path(user_input)
        if file_path and os.path.exists(file_path):
            return self._analyze_file(file_path, user_input)

        # 일반 데이터 관련 질문
        return self._data_question(user_input, context)

    def _extract_file_path(self, text):
        """텍스트에서 파일 경로 추출."""
        for word in text.split():
            if any(word.endswith(ext)
                   for ext in [".csv", ".xlsx", ".json", ".tsv"]):
                if os.path.exists(word):
                    return word
                # 현재 디렉토리에서 탐색
                base = os.path.basename(word)
                if os.path.exists(base):
                    return base
        return None

    def _analyze_file(self, file_path, user_input):
        """CSV/JSON 파일 분석."""
        try:
            import csv

            ext = os.path.splitext(file_path)[1].lower()

            if ext == ".csv":
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)

                if not rows:
                    return {"status": "success",
                            "summary": "📊 빈 CSV 파일입니다."}

                headers = list(rows[0].keys())
                n_rows = len(rows)

                # 기본 통계
                stats = f"📊 파일: {os.path.basename(file_path)}\n"
                stats += f"행: {n_rows}개, 열: {len(headers)}개\n"
                stats += f"컬럼: {', '.join(headers[:10])}\n"

                # 처음 3행 샘플
                sample = "\n".join([str(r) for r in rows[:3]])

                # LLM으로 분석
                prompt = f"""CSV 데이터 분석:
파일: {os.path.basename(file_path)}
행: {n_rows}, 열: {len(headers)}
컬럼: {headers}
샘플 데이터:
{sample}

사용자 요청: {user_input}
한국어로 데이터 분석 결과를 요약해줘."""

                payload = json.dumps({
                    "model": "qwen2.5:14b",
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.3},
                }).encode()

                req = urllib.request.Request(
                    OLLAMA_API, data=payload,
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.loads(r.read())

                analysis = data["message"]["content"].strip()
                return {
                    "status": "success",
                    "summary": f"{stats}\n{analysis[:400]}",
                    "data": {"rows": n_rows, "columns": headers},
                }

            elif ext == ".json":
                with open(file_path, "r", encoding="utf-8") as f:
                    jdata = json.load(f)

                if isinstance(jdata, list):
                    return {
                        "status": "success",
                        "summary": f"📊 JSON 파일: {len(jdata)}개 항목",
                    }
                else:
                    return {
                        "status": "success",
                        "summary": f"📊 JSON 파일: {len(jdata)}개 키",
                    }

        except Exception as e:
            return {"status": "error", "summary": f"파일 분석 실패: {e}"}

        return {"status": "error", "summary": "지원하지 않는 파일 형식"}

    def _kaggle_search(self, user_input):
        """Kaggle 데이터셋 검색."""
        try:
            # 검색 쿼리 추출
            query = user_input.replace("kaggle", "").strip()[:50]
            q = urllib.parse.quote(query)

            url = f"https://www.kaggle.com/api/v1/datasets/list?search={q}"
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0")
            with urllib.request.urlopen(req, timeout=10) as r:
                datasets = json.loads(r.read())

            if datasets:
                lines = ["📊 Kaggle 검색 결과:"]
                for ds in datasets[:5]:
                    title = ds.get("title", ds.get("ref", "?"))
                    lines.append(f"  • {title}")
                return {"status": "success", "summary": "\n".join(lines)}

        except Exception:
            pass

        return {
            "status": "success",
            "summary": f"📊 Kaggle 검색은 API 키 설정 후 사용 가능합니다.",
        }

    def _data_question(self, user_input, context=None):
        """일반 데이터 관련 질문."""
        return {
            "status": "success",
            "summary": ("📊 데이터 분석 에이전트입니다.\n"
                       "CSV/JSON 파일 경로를 포함하여 요청하거나,\n"
                       "'kaggle [검색어]'로 데이터셋을 검색할 수 있습니다."),
        }
