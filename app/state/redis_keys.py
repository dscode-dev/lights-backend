# app/state/redis_keys.py

"""
Contrato único de chaves Redis do sistema.

⚠️ NUNCA usar strings hardcoded fora deste arquivo.
"""

# =========================
# PLAYLIST
# =========================

# Lista ordenada de steps
# type: List[PlaylistStep]
PLAYLIST_STEPS_KEY = "playlist:steps"

# =========================
# PLAYER / EXECUTOR
# =========================

# Estado global do player
# {
#   isPlaying: bool
#   activeIndex: int
#   elapsedMs: int
#   bpm: int
#   palette: str
#   currentTitle: str
#   currentType: str
# }
PLAYER_STATUS_KEY = "player:status"

# =========================
# ESP / DEVICES
# =========================

# Lista de nós ESP conhecidos pelo backend
# type: List[{
#   id: str
#   ip: str
#   role: str
# }]
ESP_NODES_KEY = "esp:nodes"

# =========================
# EVENTS / WS
# =========================

# Canal Pub/Sub único
EVENTS_CHANNEL = "events:pubsub"