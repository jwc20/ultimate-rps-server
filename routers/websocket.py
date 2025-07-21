import json
from typing import Optional
import anyio
import jwt
from broadcaster import Broadcast
from fastapi import APIRouter, Depends, Query, WebSocket, status
from sqlmodel import Session, select
from database import get_session
from models import Message, Room
from game import GameState, game_states
from rps import FixedActionPlayer, Game
from enc_library import EncLibrary
from config import SECRET_KEY, ALGORITHM, REDIS_URL

router = APIRouter()
broadcast = Broadcast(REDIS_URL)


async def chatroom_ws_receiver(
    websocket: WebSocket, room_id: str, user_id: str, session: Session
):
    if room_id not in game_states:
        room = session.exec(select(Room).where(Room.id == int(room_id))).first()
        if room:
            game_states[room_id] = GameState(
                int(room_id), room.max_players, room.number_of_actions
            )

    game_state = game_states.get(room_id)
    if game_state:
        game_state.add_player(user_id)

        await broadcast.publish(
            channel=f"chatroom_{room_id}",
            message=json.dumps(
                {
                    "type": "player_joined",
                    "username": user_id,
                    "players": game_state.get_active_players(),
                }
            ),
        )

    async for message in websocket.iter_text():
        try:
            msg_data = json.loads(message)

            if msg_data.get("type") == "play" and game_state:
                action = int(msg_data.get("message", 0))
                game_state.submit_action(user_id, action)

                await broadcast.publish(
                    channel=f"chatroom_{room_id}",
                    message=json.dumps(
                        {
                            "type": "player_ready",
                            "username": user_id,
                            "ready_count": len(game_state.current_round_actions),
                            "total_active": len(game_state.get_active_players()),
                        }
                    ),
                )

                if game_state.all_players_ready():
                    players = []
                    actions = []
                    for username, action in game_state.current_round_actions.items():
                        players.append(FixedActionPlayer(username, action))
                        actions.append(action)

                    game = Game(players, game_state.number_of_actions)
                    eliminated_indices = game.eliminate(actions)

                    eliminated_usernames = []
                    for idx in eliminated_indices:
                        username = players[idx].name
                        eliminated_usernames.append(username)
                        game_state.eliminated_players.add(username)

                    remaining_players = game_state.get_active_players()

                    await broadcast.publish(
                        channel=f"chatroom_{room_id}",
                        message=json.dumps(
                            {
                                "type": "round_complete",
                                "round": game_state.round_number,
                                "actions": game_state.current_round_actions,
                                "eliminated": eliminated_usernames,
                                "remaining": remaining_players,
                                "game_over": len(remaining_players) == 1,
                            }
                        ),
                    )

                    if len(remaining_players) > 1:
                        game_state.reset_round()
                    else:
                        winner = remaining_players[0] if remaining_players else None
                        game_state.game_over = True
                        game_state.winner = winner
                        await broadcast.publish(
                            channel=f"chatroom_{room_id}",
                            message=json.dumps({"type": "game_over", "winner": winner}),
                        )

            elif (
                msg_data.get("type") == "reset_game"
                and game_state
                and game_state.game_over
            ):
                game_state.reset()
                await broadcast.publish(
                    channel=f"chatroom_{room_id}",
                    message=json.dumps(
                        {
                            "type": "game_reset",
                            "players": game_state.get_active_players(),
                        }
                    ),
                )
            else:
                db_message = Message(
                    room_id=int(room_id),
                    username=msg_data.get("username", user_id),
                    message=msg_data.get("message", ""),
                    type=msg_data.get("type", "message"),
                )
                session.add(db_message)
                session.commit()

                await broadcast.publish(channel=f"chatroom_{room_id}", message=message)

        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error processing message: {e}")


async def chatroom_ws_sender(websocket: WebSocket, room_id: str, user_id: str):
    enc = EncLibrary()
    async with broadcast.subscribe(channel=f"chatroom_{room_id}") as subscriber:
        async for event in subscriber:
            key = "buttfart"
            await websocket.send_text(event.message)


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    session: Optional[Session] = Depends(get_session),
    token: Optional[str] = Query(None),
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.accept()

        messages = session.exec(
            select(Message)
            .where(Message.room_id == int(room_id))
            .order_by(Message.created_at)
            .limit(50)
        ).all()

        for msg in messages:
            history_msg = {
                "username": msg.username,
                "message": msg.message,
                "type": msg.type,
                "timestamp": msg.created_at.isoformat(),
            }
            await websocket.send_text(json.dumps(history_msg))

        async with anyio.create_task_group() as task_group:
            async def run_chatroom_ws_receiver() -> None:
                await chatroom_ws_receiver(
                    websocket=websocket,
                    room_id=room_id,
                    user_id=user_id,
                    session=session,
                )
                task_group.cancel_scope.cancel()

            task_group.start_soon(run_chatroom_ws_receiver)
            await chatroom_ws_sender(
                websocket=websocket, room_id=room_id, user_id=user_id
            )

    except jwt.InvalidTokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)