"""
huggingface_mcp.py — HuggingFace 모델/데이터셋 검색 MCP 서버

노출 도구:
  1. search_models    — HuggingFace Hub 모델 검색
  2. search_datasets  — HuggingFace Hub 데이터셋 검색
  3. model_info       — 특정 모델 상세 정보 (파라미터 수, 라이선스, 태스크)
  4. download_model   — 모델 카드 및 기본 정보 다운로드 (실제 가중치 제외)

사용법:
  python mcp_servers/huggingface_mcp.py
"""

import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.resolve()
HF_CACHE_DIR = BASE_DIR / "downloads" / "huggingface"
HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

HF_TOKEN = os.environ.get("HUGGINGFACE_TOKEN", "")  # 선택사항

TOOL_LIST = [
    {
        "name": "search_models",
        "description": "HuggingFace Hub에서 모델 검색. 태스크, 라이브러리, 언어 필터 지원.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색 키워드 (예: 'anomaly detection', 'object detection')"},
                "task": {"type": "string", "description": "태스크 필터 (예: image-classification, object-detection, text-classification)"},
                "library": {"type": "string", "description": "라이브러리 필터 (예: pytorch, transformers, diffusers)"},
                "max_results": {"type": "integer", "description": "최대 결과 수 (기본 10, 최대 20)"},
                "sort": {"type": "string", "description": "정렬: downloads, likes, lastModified (기본 downloads)"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_datasets",
        "description": "HuggingFace Hub에서 데이터셋 검색",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색 키워드"},
                "task": {"type": "string", "description": "태스크 필터"},
                "max_results": {"type": "integer", "description": "최대 결과 수 (기본 10)"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "model_info",
        "description": "특정 HuggingFace 모델의 상세 정보 조회 (태스크, 아키텍처, 라이선스, 파라미터 수)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "모델 ID (예: 'openai/whisper-large-v3' 또는 'microsoft/resnet-50')"},
            },
            "required": ["model_id"]
        }
    },
    {
        "name": "download_model_card",
        "description": "HuggingFace 모델 카드(README) 다운로드 및 내용 반환",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "모델 ID"},
                "save_local": {"type": "boolean", "description": "로컬 저장 여부 (기본 True)"},
            },
            "required": ["model_id"]
        }
    },
]


def tool_search_models(arguments: dict) -> dict:
    """HuggingFace 모델 검색."""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return {"error": "huggingface-hub 패키지가 설치되지 않았습니다. pip install huggingface-hub 실행 필요"}

    query = arguments.get("query", "")
    task = arguments.get("task", None)
    library = arguments.get("library", None)
    max_results = min(int(arguments.get("max_results", 10)), 20)
    sort = arguments.get("sort", "downloads")

    if not query:
        return {"error": "검색 쿼리가 필요합니다"}

    try:
        api = HfApi(token=HF_TOKEN if HF_TOKEN else None)
        models = api.list_models(
            search=query,
            task=task,
            library=library,
            sort=sort,
            direction=-1,
            limit=max_results,
            cardData=True,
        )

        results = []
        for m in models:
            results.append({
                "model_id": m.modelId,
                "task": m.pipeline_tag or "",
                "downloads_last_month": getattr(m, 'downloads', 0) or 0,
                "likes": getattr(m, 'likes', 0) or 0,
                "library": getattr(m, 'library_name', "") or "",
                "language": getattr(m, 'language', []) or [],
                "tags": (m.tags or [])[:10],
                "last_modified": str(getattr(m, 'lastModified', "")) or "",
                "url": f"https://huggingface.co/{m.modelId}",
            })

        return {
            "success": True,
            "query": query,
            "count": len(results),
            "models": results
        }
    except Exception as e:
        return {"success": False, "error": f"모델 검색 오류: {e}"}


def tool_search_datasets(arguments: dict) -> dict:
    """HuggingFace 데이터셋 검색."""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return {"error": "huggingface-hub 패키지가 설치되지 않았습니다"}

    query = arguments.get("query", "")
    task = arguments.get("task", None)
    max_results = min(int(arguments.get("max_results", 10)), 20)

    if not query:
        return {"error": "검색 쿼리가 필요합니다"}

    try:
        api = HfApi(token=HF_TOKEN if HF_TOKEN else None)
        datasets = api.list_datasets(
            search=query,
            task_categories=task,
            sort="downloads",
            direction=-1,
            limit=max_results,
        )

        results = []
        for ds in datasets:
            results.append({
                "dataset_id": ds.id,
                "downloads": getattr(ds, 'downloads', 0) or 0,
                "likes": getattr(ds, 'likes', 0) or 0,
                "tags": (ds.tags or [])[:10],
                "task_categories": getattr(ds, 'task_categories', []) or [],
                "last_modified": str(getattr(ds, 'lastModified', "")) or "",
                "url": f"https://huggingface.co/datasets/{ds.id}",
            })

        return {
            "success": True,
            "query": query,
            "count": len(results),
            "datasets": results
        }
    except Exception as e:
        return {"success": False, "error": f"데이터셋 검색 오류: {e}"}


def tool_model_info(arguments: dict) -> dict:
    """특정 모델 상세 정보 조회."""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return {"error": "huggingface-hub 패키지가 설치되지 않았습니다"}

    model_id = arguments.get("model_id", "").strip()
    if not model_id:
        return {"error": "모델 ID가 필요합니다"}

    try:
        api = HfApi(token=HF_TOKEN if HF_TOKEN else None)
        info = api.model_info(model_id, securityStatus=False)

        # 모델 카드에서 파라미터 수 추출 시도
        param_count = None
        if hasattr(info, 'cardData') and info.cardData:
            param_count = info.cardData.get('model-index', [{}])[0].get('results', [{}])[0].get('metrics', [{}])[0].get('value') if info.cardData.get('model-index') else None

        # 사이브 정보 (config.json에서)
        config = {}
        try:
            import json as _json
            import urllib.request as _req
            config_url = f"https://huggingface.co/{model_id}/raw/main/config.json"
            r = _req.urlopen(config_url, timeout=10)
            config = _json.loads(r.read())
        except Exception:
            pass

        return {
            "success": True,
            "model_id": info.modelId,
            "task": info.pipeline_tag or "",
            "library": getattr(info, 'library_name', "") or "",
            "language": getattr(info, 'language', []) or [],
            "license": info.cardData.get('license', '') if info.cardData else "",
            "tags": (info.tags or [])[:20],
            "downloads": getattr(info, 'downloads', 0) or 0,
            "likes": getattr(info, 'likes', 0) or 0,
            "url": f"https://huggingface.co/{model_id}",
            "config_preview": {k: v for k, v in list(config.items())[:10]} if config else {},
            "architectures": config.get("architectures", []) if config else [],
            "parameter_hint": param_count,
        }
    except Exception as e:
        return {"success": False, "error": f"모델 정보 조회 오류: {e}"}


def tool_download_model_card(arguments: dict) -> dict:
    """모델 카드 README 다운로드."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return {"error": "huggingface-hub 패키지가 설치되지 않았습니다"}

    model_id = arguments.get("model_id", "").strip()
    save_local = arguments.get("save_local", True)

    if not model_id:
        return {"error": "모델 ID가 필요합니다"}

    try:
        # 모델 카드 URL 직접 fetch (API 호출 없이)
        import urllib.request
        readme_url = f"https://huggingface.co/{model_id}/raw/main/README.md"
        req = urllib.request.Request(
            readme_url,
            headers={"User-Agent": "AgenticCCIFPS/1.0"}
        )
        if HF_TOKEN:
            req.add_header("Authorization", f"Bearer {HF_TOKEN}")

        with urllib.request.urlopen(req, timeout=30) as r:
            content = r.read().decode("utf-8")

        if save_local:
            safe_name = model_id.replace("/", "_")
            save_path = HF_CACHE_DIR / f"{safe_name}_README.md"
            save_path.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "model_id": model_id,
            "content_length": len(content),
            "content": content[:5000],  # 처음 5000자
            "saved_to": str(save_path) if save_local else None,
            "url": f"https://huggingface.co/{model_id}",
        }
    except Exception as e:
        return {"success": False, "error": f"모델 카드 다운로드 오류: {e}"}


TOOL_HANDLERS = {
    "search_models": tool_search_models,
    "search_datasets": tool_search_datasets,
    "model_info": tool_model_info,
    "download_model_card": tool_download_model_card,
}


def handle_request(request: dict):
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "huggingface-mcp", "version": "1.0.0"},
            }
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOL_LIST}}

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            result_content = json.dumps({"error": f"알 수 없는 도구: {tool_name}"})
            is_error = True
        else:
            try:
                result_content = json.dumps(handler(arguments), ensure_ascii=False)
                is_error = False
            except Exception as e:
                result_content = json.dumps({"error": str(e)})
                is_error = True

        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": result_content}],
            "isError": is_error,
        }}

    if req_id is not None:
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return None


def main():
    """Stdio JSON-RPC 2.0 서버 메인 루프."""
    sys.stderr.write(f"[huggingface-mcp] v1.0 서버 시작 (PID={os.getpid()})\n")
    auth_status = "✅ 토큰 설정됨" if HF_TOKEN else "⚠️ 미인증 (공개 모델만 접근 가능)"
    sys.stderr.write(f"[huggingface-mcp] 인증 상태: {auth_status}\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()

    sys.stderr.write("[huggingface-mcp] 서버 종료\n")


if __name__ == "__main__":
    main()
