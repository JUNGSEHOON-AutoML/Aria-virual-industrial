import os
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional

def get_current_time_str() -> str:
    """현재 연/월/일/요일/시간을 한글 포맷으로 변환해 반환합니다."""
    now = datetime.now()
    weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    weekday = weekdays[now.weekday()]
    ampm = "오전" if now.hour < 12 else "오후"
    hour = now.hour if now.hour <= 12 else now.hour - 12
    if hour == 0:
        hour = 12
    return f"현재 서버 시간: {now.year}년 {now.month}월 {now.day}일 {weekday} {ampm} {hour}시 {now.minute}분"

class AgentState(BaseModel):
    """
    공용 상태 객체 (Agent State Management).
    자율 협업 아키텍처 내에서 에이전트 간 주고받는 상태 데이터를 표현합니다.
    """
    input_file: Optional[str] = ""
    user_request: Optional[str] = ""
    vision_extracted_data: Optional[str] = None
    web_research_data: Optional[str] = None
    next_agent: Optional[str] = "ROUTER"
    is_completed: bool = False
    step_count: int = 0
    history: List[str] = []
    chat_id: Optional[str] = None
    final_report: Optional[str] = None
    current_time: str = Field(default_factory=get_current_time_str)
    operator_success: Optional[bool] = None
    critic_error_log: Optional[str] = None
    critic_executed_code: Optional[str] = None
    critic_screenshot_path: Optional[str] = None
    critic_retry_count: int = 0
    handoff_code: Optional[str] = None
    chat_history: Optional[List[dict]] = Field(default_factory=list)

def get_lightweight_summary(state: AgentState) -> str:
    """
    라우터 에이전트의 프롬프트 주입용 경량화 상태 요약 생성 함수.
    대규모 원본 데이터 대신 길이 및 요약 메타데이터를 전송하여 토큰을 절약합니다.
    """
    file_info = os.path.basename(state.input_file) if state.input_file else "없음 (일반 대화/명령)"
    summary_parts = [
        f"서버 시간: {state.current_time}",
        f"사용자 요청: {state.user_request}",
        f"파일 정보: {file_info}",
        f"현재 노드: {state.next_agent}",
        f"실행 횟수: {state.step_count} / 5",
        f"완료 여부: {state.is_completed}"
    ]
    
    if state.handoff_code:
        summary_parts.append(f"- 위임된 코드 (Handoff Code): [보유 중] (길이: {len(state.handoff_code)}자)")
        
    if state.operator_success is not None:
        summary_parts.append(f"- OPERATOR 수행 결과: {'성공' if state.operator_success else '실패'}")
        
    if state.critic_retry_count > 0:
        summary_parts.append(f"- CRITIC 자가 수정 재시도 횟수: {state.critic_retry_count} / 3")
        
    if state.critic_error_log:
        summary_parts.append(f"- 최근 발생 에러 로그: {state.critic_error_log[:500]}")
        
    if state.critic_executed_code:
        summary_parts.append(f"- 에러 발생 시 실행 코드: {state.critic_executed_code[:500]}")
        
    if state.vision_extracted_data:
        summary_parts.append(f"- VISION 데이터: [분석 완료] (텍스트 길이: {len(state.vision_extracted_data)}자)")
    else:
        summary_parts.append("- VISION 데이터: [추출 대기 중]")
        
    if state.web_research_data:
        summary_parts.append(f"- DIPLOMAT 리서치 데이터: [리서치 완료] (텍스트 길이: {len(state.web_research_data)}자)")
    else:
        summary_parts.append("- DIPLOMAT 리서치 데이터: [검증 대기 중]")
        
    if state.final_report:
        summary_parts.append(f"- 최종 보고서: [작성 완료] (길이: {len(state.final_report)}자)")
    else:
        summary_parts.append("- 최종 보고서: [작성 대기 중]")
        
    if state.history:
        summary_parts.append("수행 이력:")
        for h in state.history:
            summary_parts.append(f"  * {h}")
            
    if state.chat_history:
        summary_parts.append("최근 대화 기록 (Conversation Context):")
        for h in state.chat_history[-6:]:
            role = "사용자" if h.get("role") == "user" else "ARIA"
            content = h.get("content", "")
            if len(content) > 100:
                content = content[:100] + "..."
            summary_parts.append(f"  * {role}: {content}")
            
    return "\n".join(summary_parts)
