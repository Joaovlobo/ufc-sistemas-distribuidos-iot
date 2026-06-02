#!/bin/bash
echo "Iniciando Backend do Dashboard (FastAPI)..."
source .venv/bin/activate
python dashboard/api.py &
API_PID=$!

echo "Iniciando Frontend do Dashboard (React/Vite)..."
cd dashboard/web
npm run dev &
FRONTEND_PID=$!

echo ""
echo "=========================================================="
echo "🌟 Dashboard Interativo Smart City iniciado!"
echo "🔗 Acesse no navegador: http://localhost:5173"
echo "=========================================================="
echo "Pressione Ctrl+C para encerrar o Dashboard."

trap "kill $API_PID $FRONTEND_PID; exit" INT TERM
wait
