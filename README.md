⸻

🎆 LED Show Orchestrator

Sistema profissional de orquestração de shows de LEDs, portal e holograma, controlado por ESP32, com execução de áudio, sincronização em tempo real e controle via frontend web.

O backend atua como cérebro do show, enquanto o frontend é apenas interface reativa.

⸻

🧠 Visão Geral da Arquitetura

Frontend (Next.js)
   │
   │ HTTP + WebSocket
   ▼
Backend (FastAPI)
   │
   ├── Redis (estado em tempo real)
   ├── MongoDB (persistência)
   ├── Player Executor (loop de execução)
   ├── Pipeline YouTube (yt-dlp + BPM)
   ├── Pipeline Presentation (MP3 + JSON)
   └── ESP32 (HTTP JSON)


⸻

🚀 Funcionalidades Principais

🎵 Playlist Inteligente
	•	Múltiplos steps
	•	Tipos suportados:
	•	music (YouTube → MP3)
	•	presentation (MP3 + sequência fechada)
	•	pause
	•	Steps com status:
	•	processing
	•	ready
	•	error

⸻

▶️ Player Executor (Tempo Real)
	•	Loop de execução próprio
	•	elapsedMs confiável
	•	Um único step ativo por vez
	•	Avanço automático por duração
	•	Controle total via HTTP

⸻

🔁 WebSocket em Tempo Real
	•	/ws como fonte de verdade
	•	Eventos enviados:
	•	status
	•	playlist_progress
	•	playlist_ready
	•	playlist_error
	•	esp

⸻

🤖 Integração com ESP32
	•	Comunicação via HTTP (JSON)
	•	Comandos simples:
	•	beat
	•	set_palette
	•	set_mode
	•	portal_mode
	•	hologram_behavior
	•	Execução determinística

⸻

🧩 Tipos de Step

🎶 Music
	•	Criado via YouTube
	•	Pipeline:
	1.	Download com yt-dlp
	2.	Conversão para MP3
	3.	Análise de BPM e duração
	4.	Geração automática de beats
	•	LEDs reagem ao BPM

⸻

🎤 Presentation
	•	Criado via upload
	•	Recebe:
	•	MP3
	•	JSON com timeline de comandos
	•	Sem beat automático
	•	Execução exata da sequência enviada

Exemplo de timeline:

{
  "version": 1,
  "timeline": [
    { "atMs": 0, "target": "broadcast", "type": "set_palette", "payload": { "palette": "blue" } },
    { "atMs": 1200, "target": "portal", "type": "portal_mode", "payload": { "mode": "open" } }
  ]
}


⸻

🔌 Endpoints HTTP

Playlist
	•	GET /playlist
	•	POST /playlist/add-from-youtube
	•	POST /playlist/add-presentation
	•	PUT /playlist/edit/{index}
	•	DELETE /playlist/delete/{index}

Player
	•	POST /play
	•	POST /pause
	•	POST /skip
	•	POST /play-step

ESP
	•	GET /esp/status
	•	POST /esp/refresh

Status
	•	GET /status

⸻

🔁 WebSocket (/ws)

Eventos emitidos:

{ "type": "status", "data": PlayerStatus }
{ "type": "playlist_progress", "data": { "stepId": "...", "progress": 0.5 } }
{ "type": "playlist_ready", "data": { "step": PlaylistStep } }
{ "type": "playlist_error", "data": { "stepId": "...", "error": "..." } }
{ "type": "esp", "data": { "nodes": [...] } }


⸻

🗂️ Estrutura do Projeto

backend/
 ├── app/
 │   ├── api/
 │   ├── services/
 │   ├── state/
 │   ├── ws/
 │   ├── models/
 │   └── main.py
 ├── media/ (gerado automaticamente)
 ├── docker/
 └── pyproject.toml

frontend/
 ├── app/
 ├── services/
 ├── hooks/
 └── stores/


⸻

⚙️ Setup Local

Pré-requisitos
	•	Python 3.11+
	•	Node.js 18+
	•	Docker
	•	ffmpeg instalado
	•	Redis
	•	MongoDB

⸻

Subir infra local

docker compose up -d


⸻

Backend

cd backend
cp .env.example .env
uvicorn app.main:app --reload


⸻

Frontend

cd frontend
npm install
npm run dev


⸻

🔒 Variáveis de Ambiente (Backend)

REDIS_URL=redis://localhost:6379/0
MONGO_URL=mongodb://localhost:27017
MEDIA_DIR=./media
ESP_REGISTRY=right=192.168.0.50,left=192.168.0.51


⸻

🧠 Regras Importantes
	•	❌ Frontend não calcula tempo
	•	❌ Frontend não gera beat
	•	❌ Frontend não executa lógica
	•	✅ Backend é única fonte de verdade
	•	✅ WebSocket dirige o estado visual
	•	✅ Steps processing são inativos
	•	✅ Steps presentation executam sequência fechada

⸻

🧪 Testes Manuais Recomendados
	1.	Adicionar música via YouTube
	2.	Acompanhar progress no WS
	3.	Ver step virar ready
	4.	POST /play
	5.	Confirmar beats nos ESPs
	6.	Adicionar presentation
	7.	Validar execução da timeline

⸻

📌 Próximos Passos (Roadmap)
	•	🔊 Player de áudio local sincronizado
	•	🧪 Simulador visual de timeline
	•	🛠️ Editor visual de apresentação
	•	📊 Observabilidade (metrics)
	•	🔐 Autenticação / multi-usuário

⸻

🥷 Filosofia do Projeto

Backend pensa.
Frontend reage.
ESP executa.

Sistema determinístico, previsível e robusto, pronto para shows reais.

⸻

Se quiser, no próximo passo posso:
	•	adaptar o README para open-source
	•	gerar versão em inglês
	•	adicionar diagrama ASCII
	•	criar checklist de QA
	•	escrever documentação da API (OpenAPI)

É só mandar.