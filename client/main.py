import socket
import sys
import os
import time
import struct
from datetime import datetime
import os
import time
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from proto import messages_pb2

GATEWAY_IP = '127.0.0.1'
GATEWAY_TCP_PORT = 5001

def send_request(req):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((GATEWAY_IP, GATEWAY_TCP_PORT))
        req_data = req.SerializeToString()
        sock.sendall(struct.pack('>I', len(req_data)) + req_data)
        
        size_data = sock.recv(4)
        if not size_data or len(size_data) < 4:
            sock.close()
            return None
            
        size = struct.unpack('>I', size_data)[0]
        data = b''
        while len(data) < size:
            packet = sock.recv(size - len(data))
            if not packet:
                break
            data += packet
            
        sock.close()
        
        resp = messages_pb2.ClientResponse()
        if data:
            resp.ParseFromString(data)
        return resp
    except Exception as e:
        print(f"\n[!] Erro de conexão com o Gateway: {e}")
        return None

def listar_fontes():
    req = messages_pb2.ClientRequest()
    req.type = messages_pb2.ClientRequest.LIST_SOURCES
    
    resp = send_request(req)
    if resp and resp.success:
        print("\n=== Fontes Conectadas ===")
        if not resp.sources:
            print("Nenhuma fonte conectada no momento.")
        for s in resp.sources:
            print(f"- ID: {s.source_id} | Tipo: {s.type} | Estado: {s.state}")
    else:
        print("Falha ao obter lista de fontes.")

def enviar_comando():
    print("\n=== Enviar Comando ===")
    source_id = input("ID da fonte: ")
    cmd = input("Comando (ex: LIGAR, DESLIGAR, SET_STATE, SET_RESOLUTION, SET_FREQ, SET_LIMIAR, SET_CYCLE, SET_INTENSITY): ")
    param = input("Parâmetro (deixe em branco se não houver): ")
    
    req = messages_pb2.ClientRequest()
    req.type = messages_pb2.ClientRequest.CONTROL_COMMAND
    req.control_command.source_id = source_id
    req.control_command.command = cmd
    req.control_command.parameter = param
    
    resp = send_request(req)
    if resp:
        if resp.success:
            print(f"\n[SUCESSO] {resp.message}")
        else:
            print(f"\n[ERRO] {resp.message}")

def consultar_historico():
    print("\n=== Histórico de Leituras ===")
    tipo = input("Filtrar por tipo (deixe em branco para todos): ")
    
    req = messages_pb2.ClientRequest()
    req.type = messages_pb2.ClientRequest.GET_HISTORY
    if tipo:
        req.filter_type = tipo
        
    resp = send_request(req)
    if resp and resp.success:
        print(f"\nÚltimas leituras (Filtro: {tipo if tipo else 'Todos'}):")
        for r in resp.history:
            dt = datetime.fromtimestamp(r.timestamp).strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{dt}] {r.source_id} ({r.type}): {r.value} {r.unit}")
    else:
        print("Falha ao obter histórico.")

def consultar_agregacao():
    print("\n=== Consulta Agregada (Média) ===")
    tipo = input("Tipo de fonte para agregação (ex: temperatura, qualidade_ar): ")
    if not tipo:
        print("Tipo é obrigatório.")
        return
        
    req = messages_pb2.ClientRequest()
    req.type = messages_pb2.ClientRequest.GET_AGGREGATION
    req.filter_type = tipo
    
    resp = send_request(req)
    if resp and resp.success:
        print(f"\n{resp.message}")
        print(f"Resultado Agregado: {resp.aggregation_result:.2f}")
    else:
        print("Falha ao obter agregação.")

def main():
    while True:
        print("\n" + "="*30)
        print(" CLIENTE ANALÍTICO - SMART CITY ")
        print("="*30)
        print("1. Listar Fontes")
        print("2. Enviar Comando de Controle")
        print("3. Consultar Histórico (Últimos 50)")
        print("4. Consultar Agregação (Média)")
        print("5. Sair")
        
        op = input("\nEscolha uma opção: ")
        
        if op == '1':
            listar_fontes()
        elif op == '2':
            enviar_comando()
        elif op == '3':
            consultar_historico()
        elif op == '4':
            consultar_agregacao()
        elif op == '5':
            print("Saindo...")
            break
        else:
            print("Opção inválida.")

if __name__ == '__main__':
    main()
