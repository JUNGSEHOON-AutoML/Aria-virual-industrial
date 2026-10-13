"""Read-only access to the same offline L1 JSON used by Markdown reports."""
import re
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from .store import ROOT
router=APIRouter(prefix='/api/dt/vision')
AUDIT=ROOT/'docs/reports/vision_audit'
CLASSES={'bottle','screw','carpet'};MODELS={'coreset','ccifps','random_same_k'}
def folder(cls,model=None):
 if cls not in CLASSES or model is not None and model not in MODELS:raise HTTPException(404,'Unknown audit')
 return AUDIT/cls/model if model else AUDIT/cls
@router.get('/{cls}/report')
def report(cls:str):
 path=folder(cls)/'report.json'
 if not path.is_file():raise HTTPException(404,'비전 분석 생성 대기')
 return FileResponse(path,media_type='application/json',headers={'Cache-Control':'no-cache'})
@router.get('/{cls}/{model}/distribution.svg')
def distribution(cls:str,model:str):
 path=folder(cls,model)/'distribution.svg'
 if not path.is_file():raise HTTPException(404,'Distribution not generated')
 return FileResponse(path,media_type='image/svg+xml')
@router.get('/{cls}/{model}/assets/{key}/{name}')
def asset(cls:str,model:str,key:str,name:str):
 root=folder(cls,model)/'outputs/factory-evidence'
 if not re.fullmatch('[a-f0-9]{32}',key) or name not in {'source.png','original.png','overlay.png','gt_mask.png','object_proxy.png'}:raise HTTPException(404,'Unknown evidence asset')
 path=root/key/name
 if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):raise HTTPException(404,'Evidence not generated')
 return FileResponse(path,media_type='image/png')
