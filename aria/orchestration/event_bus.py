import asyncio
import logging
from typing import Dict, List, Callable, Any

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("argus.event_bus")

class EventBus:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(EventBus, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._subscribers: Dict[str, List[Callable[[Any], Any]]] = {}
        self._queue: asyncio.Queue = None
        self._loop_task: asyncio.Task = None
        self._initialized = True

    @property
    def queue(self) -> asyncio.Queue:
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    def subscribe(self, topic: str, callback: Callable[[Any], Any]):
        """특정 토픽(주제)에 비동기 콜백을 등록합니다."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        if callback not in self._subscribers[topic]:
            self._subscribers[topic].append(callback)
            logger.info(f"Subscribed callback {callback.__name__ if hasattr(callback, '__name__') else callback} to topic '{topic}'")

    def unsubscribe(self, topic: str, callback: Callable[[Any], Any]):
        """등록된 콜백을 해제합니다."""
        if topic in self._subscribers and callback in self._subscribers[topic]:
            self._subscribers[topic].remove(callback)
            logger.info(f"Unsubscribed callback {callback.__name__ if hasattr(callback, '__name__') else callback} from topic '{topic}'")

    async def publish(self, topic: str, data: Any):
        """이벤트 버스에 특정 주제로 데이터를 발행합니다."""
        await self.queue.put((topic, data))
        logger.info(f"Published event to topic '{topic}': {data}")

    def publish_sync(self, topic: str, data: Any):
        """동기식 컨텍스트에서 이벤트를 발행할 수 있도록 지원합니다."""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.publish(topic, data))
            else:
                asyncio.run(self.publish(topic, data))
        except RuntimeError:
            # 실행 중인 루프가 없는 경우 새 루프로 실행
            try:
                asyncio.run(self.publish(topic, data))
            except Exception as e:
                logger.error(f"Failed to publish sync event to topic '{topic}': {e}")

    async def start(self):
        """이벤트 버스 처리 루프를 백그라운드에서 시작합니다."""
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._process_queue())
            logger.info("EventBus background processing loop started.")

    async def stop(self):
        """이벤트 버스를 정지합니다."""
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            logger.info("EventBus background processing loop stopped.")

    async def _process_queue(self):
        while True:
            try:
                topic, data = await self.queue.get()
                if topic in self._subscribers:
                    for callback in self._subscribers[topic]:
                        asyncio.create_task(self._safe_call(callback, topic, data))
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in EventBus queue processor: {e}")
                await asyncio.sleep(1)

    async def _safe_call(self, callback: Callable, topic: str, data: Any):
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(data)
            else:
                callback(data)
        except Exception as e:
            logger.error(f"Error executing callback for topic '{topic}': {e}", exc_info=True)

# 싱글톤 인스턴스 노출
event_bus = EventBus()
