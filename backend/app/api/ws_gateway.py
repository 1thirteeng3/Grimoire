import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.fsm import FSMState, SessionContext, StateManager
from app.models.websocket import ServerEvent

router = APIRouter()
logger = logging.getLogger("grimoire.ws")


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    ctx = SessionContext(session_id=session_id)
    manager = StateManager(ctx)
    logger.info("WebSocket conectado: %s", session_id)
    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            msg_type = message.get("type")

            if msg_type == "INTENT_SUBMIT":
                await handle_intent(websocket, manager, message)
            elif msg_type == "PACT_RESOLVE":
                await handle_pact_resolve(websocket, manager, message)
            elif msg_type == "PING":
                await websocket.send_text(json.dumps({"type": "PONG"}))
            else:
                logger.warning("Tipo de mensagem desconhecido: %s", msg_type)
    except WebSocketDisconnect:
        logger.info("WebSocket desconectado: %s", session_id)


async def send_event(ws: WebSocket, event: ServerEvent) -> None:
    await ws.send_text(event.model_dump_json())


async def handle_intent(ws: WebSocket, manager: StateManager, message: dict) -> None:
    del ws, message
    manager.transition(FSMState.PERCEPTION_ROUTING)
    manager.transition(FSMState.ERROR)
    manager.transition(FSMState.IDLE)


async def handle_pact_resolve(ws: WebSocket, manager: StateManager, message: dict) -> None:
    del ws, manager, message
