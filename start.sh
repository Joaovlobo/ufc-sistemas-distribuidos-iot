#!/bin/bash
# start.sh - Script para iniciar o Gateway e os Sensores Python

echo "Inicializando o ambiente virtual..."
source .venv/bin/activate

echo "Iniciando Gateway..."
python gateway/main.py &
GATEWAY_PID=$!
sleep 2

echo "Iniciando Fonte: Temperatura..."
python sources/temperatura/main.py &
TEMP_PID=$!

echo "Iniciando Fonte: Qualidade do Ar..."
python sources/qualidade_ar/main.py &
AR_PID=$!

echo "Iniciando Fonte: Câmera..."
python sources/camera/main.py &
CAM_PID=$!

echo "Iniciando Fonte: Poste de Iluminação..."
python sources/poste_iluminacao/main.py &
POSTE_PID=$!

echo ""
echo "==============================================================="
echo "Serviços Python iniciados."
echo "Para o Semáforo (Go), rode em outro terminal:"
echo "  cd sources/semaforo && go mod tidy && go run main.go"
echo "Para abrir o Cliente:"
echo "  source .venv/bin/activate && python client/main.py"
echo "==============================================================="
echo "Pressione Ctrl+C para encerrar os serviços em background."

trap "kill $GATEWAY_PID $TEMP_PID $AR_PID $CAM_PID $POSTE_PID; exit" INT TERM
wait
