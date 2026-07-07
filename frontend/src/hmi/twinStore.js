// twinStore — signalStore 호환 어댑터. 자체 WebSocket을 더 이상 열지 않는다(단일 WS로 통합).
// 기존 import(subscribe/getLatest/subscribeStatus/getStatus/sendCmd/ensureConnected) 그대로 유지.
import {
  ensureConnected as _ensure, subscribeType, getLatestType,
  subscribeStatus as _subStatus, getStatus as _getStatus, send as _send,
} from './signalStore'

export function ensureConnected() { _ensure() }
export function subscribe(type, cb) { _ensure(); return subscribeType(type, cb) }
export function getLatest(type) { return getLatestType(type) }
export function subscribeStatus(cb) { return _subStatus(cb) }
export function getStatus() { return _getStatus() }
export function sendCmd(obj) { _send(obj) }
