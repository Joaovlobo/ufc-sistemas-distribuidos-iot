import socket
import struct
import threading
import time
import os
import csv
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from proto import messages_pb2

MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = 5000
GATEWAY_UDP_PORT = 5005
GATEWAY_TCP_PORT = 5001
CSV_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'dados_gateway.csv')

class Gateway:
    def __init__(self):
        self.sources = {} # source_id -> dict com info da fonte
        self.csv_lock = threading.Lock()
        
        # garantir csv existe e tem cabeçalho
        os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
        if not os.path.exists(CSV_FILE):
            with open(CSV_FILE, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'source_id', 'type', 'value', 'unit'])

    def send_discovery(self):
        """Envia pacote multicast solicitando registro das fontes."""
        print(f"[*] Gateway enviando discovery multicast para {MULTICAST_GROUP}:{MULTICAST_PORT}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        
        req = messages_pb2.DiscoveryRequest()
        req.gateway_ip = socket.gethostbyname(socket.gethostname())
        req.gateway_udp_port = GATEWAY_UDP_PORT
        req.gateway_tcp_port = GATEWAY_TCP_PORT
        
        msg = req.SerializeToString()
        # Adicionar prefixo para identificar o tipo de mensagem ja que UDP nao tem isso nativo 
        # 1-byte prefix: 0=DiscoveryRequest, 1=DiscoveryResponse, 2=DataReading
        sock.sendto(b'\x00' + msg, (MULTICAST_GROUP, MULTICAST_PORT))
        sock.close()

    def handle_udp_messages(self):
        """Recebe registros e leituras via UDP."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', GATEWAY_UDP_PORT))
        print(f"[*] Gateway ouvindo UDP em 0.0.0.0:{GATEWAY_UDP_PORT}")
        
        while True:
            data, addr = sock.recvfrom(4096)
            msg_type = data[0]
            payload = data[1:]
            
            if msg_type == 1: # DiscoveryResponse
                resp = messages_pb2.DiscoveryResponse()
                resp.ParseFromString(payload)
                self.sources[resp.source_id] = {
                    'type': resp.type,
                    'ip': resp.ip,
                    'tcp_port': resp.tcp_port,
                    'state': resp.initial_state,
                    'last_seen': time.time()
                }
                print(f"[+] Fonte registrada: {resp.source_id} ({resp.type}) de {resp.ip}:{resp.tcp_port}")
                
            elif msg_type == 2: # DataReading
                reading = messages_pb2.DataReading()
                reading.ParseFromString(payload)
                self.save_reading(reading)
                # print(f"[~] Leitura recebida de {reading.source_id}: {reading.value} {reading.unit}")
                
                # Update state para sensores especificos
                if reading.source_id in self.sources:
                    self.sources[reading.source_id]['last_seen'] = time.time()
                    if self.sources[reading.source_id]['state'] == 'OFFLINE':
                        self.sources[reading.source_id]['state'] = 'ONLINE (RECUPERADO)'

    def save_reading(self, reading: messages_pb2.DataReading):
        """Salva a leitura no arquivo CSV de forma thread-safe."""
        with self.csv_lock:
            with open(CSV_FILE, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([reading.timestamp, reading.source_id, reading.type, reading.value, reading.unit])

    def send_tcp_command(self, source_id, command_str, parameter):
        if source_id not in self.sources:
            return False, "Fonte não encontrada."
        
        source = self.sources[source_id]
        if source['tcp_port'] == 0:
            return False, "Fonte não controlável."
            
        cmd = messages_pb2.ControlCommand()
        cmd.source_id = source_id
        cmd.command = command_str
        cmd.parameter = parameter
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((source['ip'], source['tcp_port']))
            sock.sendall(cmd.SerializeToString())
            
            resp_data = sock.recv(4096)
            sock.close()
            
            resp = messages_pb2.ControlResponse()
            resp.ParseFromString(resp_data)
            
            if resp.success:
                # Se for mudança de estado e deu certo, atualizamos localmente o estado
                if command_str == "MUDAR_ESTADO" or command_str == "SET_STATE":
                    source['state'] = parameter
                elif command_str in ("LIGAR", "DESLIGAR"):
                    source['state'] = command_str
                
            return resp.success, resp.message
        except Exception as e:
            return False, f"Erro ao conectar com a fonte: {e}"

    def handle_client_connection(self, conn, addr):
        print(f"[*] Cliente conectado: {addr}")
        try:
            # Lê 4 bytes com o tamanho do pacote
            size_data = conn.recv(4)
            if not size_data or len(size_data) < 4:
                return
            size = struct.unpack('>I', size_data)[0]
            
            data = b''
            while len(data) < size:
                packet = conn.recv(size - len(data))
                if not packet:
                    break
                data += packet
            
            req = messages_pb2.ClientRequest()
            if data:
                req.ParseFromString(data)
            
            resp = messages_pb2.ClientResponse()
            
            if req.type == messages_pb2.ClientRequest.LIST_SOURCES:
                resp.success = True
                resp.message = "Lista de fontes"
                for sid, sdata in self.sources.items():
                    info = resp.sources.add()
                    info.source_id = sid
                    info.type = sdata['type']
                    info.state = sdata['state']
                    
            elif req.type == messages_pb2.ClientRequest.CONTROL_COMMAND:
                cmd = req.control_command
                success, msg = self.send_tcp_command(cmd.source_id, cmd.command, cmd.parameter)
                resp.success = success
                resp.message = msg
                
            elif req.type == messages_pb2.ClientRequest.GET_HISTORY:
                # Lê os últimos 50 registros
                resp.success = True
                with self.csv_lock:
                    if os.path.exists(CSV_FILE):
                        with open(CSV_FILE, mode='r') as f:
                            reader = csv.reader(f)
                            header = next(reader, None)
                            rows = list(reader)
                            # filtro opcional
                            if req.filter_type:
                                rows = [r for r in rows if r[2] == req.filter_type]
                            
                            for r in rows[-50:]:
                                rd = resp.history.add()
                                rd.timestamp = int(r[0])
                                rd.source_id = r[1]
                                rd.type = r[2]
                                rd.value = float(r[3])
                                rd.unit = r[4]
                                
            elif req.type == messages_pb2.ClientRequest.GET_AGGREGATION:
                # média dos valores para um determinado tipo
                resp.success = True
                total = 0.0
                count = 0
                with self.csv_lock:
                    if os.path.exists(CSV_FILE):
                        with open(CSV_FILE, mode='r') as f:
                            reader = csv.reader(f)
                            next(reader, None)
                            for r in reader:
                                if r[2] == req.filter_type:
                                    total += float(r[3])
                                    count += 1
                if count > 0:
                    resp.aggregation_result = total / count
                    resp.message = f"Média calculada para {req.filter_type}"
                else:
                    resp.aggregation_result = 0.0
                    resp.message = "Nenhum dado encontrado para agregação."

            resp_data = resp.SerializeToString()
            conn.sendall(struct.pack('>I', len(resp_data)) + resp_data)
        except Exception as e:
            print(f"[!] Erro ao processar requisição do cliente: {e}")
        finally:
            conn.close()

    def handle_tcp_clients(self):
        """Recebe conexões do Cliente."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', GATEWAY_TCP_PORT))
        sock.listen(5)
        print(f"[*] Gateway ouvindo TCP (Clientes) em 0.0.0.0:{GATEWAY_TCP_PORT}")
        
        while True:
            conn, addr = sock.accept()
            threading.Thread(target=self.handle_client_connection, args=(conn, addr)).start()

    def watchdog(self):
        """Monitora fontes e as marca como offline caso parem de responder"""
        while True:
            time.sleep(5)
            now = time.time()
            for sid, sdata in list(self.sources.items()):
                if sid not in ('sensor_temp_01', 'sensor_ar_01'):
                    continue
                # Se não há contato há mais de 15 segundos
                if now - sdata['last_seen'] > 15:
                    sdata['state'] = 'OFFLINE'
                    # Registra evento de falha no histórico CSV
                    reading = messages_pb2.DataReading()
                    reading.source_id = sid
                    reading.type = sdata['type']
                    reading.value = 0.0
                    reading.unit = "OFFLINE"
                    reading.timestamp = int(now)
                    self.save_reading(reading)

    def run(self):
        threading.Thread(target=self.handle_udp_messages, daemon=True).start()
        threading.Thread(target=self.handle_tcp_clients, daemon=True).start()
        threading.Thread(target=self.watchdog, daemon=True).start()
        
        # busca periodicamente por fontes em caso de falhas ou novas fontes entrando na rede
        while True:
            self.send_discovery()
            time.sleep(30)

if __name__ == '__main__':
    gw = Gateway()
    try:
        gw.run()
    except KeyboardInterrupt:
        print("Saindo...")
