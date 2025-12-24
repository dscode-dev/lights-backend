from __future__ import annotations

from app.state.playlist_state import get_playlist_raw


class PlayerExecutor:
    def __init__(self, state, ws):
        self.state = state
        self.ws = ws
        self.is_playing = False
        self.current_index = -1

    async def play(self, index: int):
        self.current_index = index
        self.is_playing = True

        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": True,
                "activeIndex": index,
            },
        })

    async def pause(self):
        self.is_playing = False

        await self.ws.broadcast({
            "type": "status",
            "data": {
                "isPlaying": False,
            },
        })

    async def next(self):
        # ✅ get_playlist_raw é FUNÇÃO do playlist_state (não é método do RedisState)
        steps = await get_playlist_raw(self.state)

        if not steps:
            return

        next_index = self.current_index + 1
        if next_index >= len(steps):
            next_index = 0  # loop simples

        await self.pause()
        await self.play(next_index)