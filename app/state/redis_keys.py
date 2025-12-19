from __future__ import annotations

# Core keys
PLAYLIST_STEPS_KEY = "playlist:steps"
PLAYER_STATUS_KEY = "player:status"
ESP_NODES_KEY = "esp:nodes"

# PubSub channel
EVENTS_CHANNEL = "events:pubsub"

def processing_key(step_id: str) -> str:
    return f"processing:{step_id}"
