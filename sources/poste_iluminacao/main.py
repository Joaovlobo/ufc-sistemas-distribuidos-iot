import socket
import struct
import time
import threading
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from proto import messages_pb2

SOURCE_ID = "poste_01"
SOURCE_TYPE = "poste_iluminacao"
MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = 5000
TCP_PORT = 6002

class PosteIluminacao:
    def __init__(self):
        self.gateway_ip = None
        self.gateway_udp_port = None
        self.running = True
        self.state = "DESLIGADO"
        self.intensidade = 100

    def get_full_state(self):
        return f"{self.state} | {self.intensidade}%"

    def listen_for_discovery(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', MULTICAST_PORT))
        mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        print(f"[*] {SOURCE_ID} aguardando discovery do Gateway...")
        while self.running:
            data, addr = sock.recvfrom(4096)
            msg_type = data[0]
            if msg_type == 0:
                req = messages_pb2.DiscoveryRequest()
                req.ParseFromString(data[1:])
                self.gateway_ip = req.gateway_ip
                self.gateway_udp_port = req.gateway_udp_port
                print(f"[+] Gateway descoberto: {self.gateway_ip}:{self.gateway_udp_port}")
                self.register_with_gateway()

    def register_with_gateway(self):
        resp = messages_pb2.DiscoveryResponse()
        resp.source_id = SOURCE_ID
        resp.type = SOURCE_TYPE
        resp.ip = socket.gethostbyname(socket.gethostname())
        resp.tcp_port = TCP_PORT
        resp.initial_state = self.get_full_state()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(b'\x01' + resp.SerializeToString(), (self.gateway_ip, self.gateway_udp_port))
        sock.close()

    def handle_tcp_control(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', TCP_PORT))
        sock.listen(5)
        print(f"[*] {SOURCE_ID} ouvindo comandos TCP na porta {TCP_PORT}")
        
        while self.running:
            conn, addr = sock.accept()
            data = conn.recv(1024)
            if data:
                cmd = messages_pb2.ControlCommand()
                cmd.ParseFromString(data)
                print(f"[<] Comando recebido: {cmd.command} {cmd.parameter}")
                
                resp = messages_pb2.ControlResponse()
                resp.source_id = SOURCE_ID
                resp.success = True
                
                if cmd.command == "LIGAR":
                    self.state = "LIGADO"
                    resp.message = "Poste ligado."
                elif cmd.command == "DESLIGAR":
                    self.state = "DESLIGADO"
                    resp.message = "Poste desligado."
                elif cmd.command == "SET_INTENSITY":
                    try:
                        self.intensidade = int(cmd.parameter)
                        resp.message = f"Intensidade ajustada para {self.intensidade}%."
                    except ValueError:
                        resp.success = False
                        resp.message = "Parâmetro de intensidade inválido."
                else:
                    resp.success = False
                    resp.message = "Comando desconhecido."
                
                if resp.success:
                    print(f"[*] Novo estado: {self.get_full_state()}")
                    if self.gateway_ip:
                        self.register_with_gateway()

                conn.sendall(resp.SerializeToString())
            conn.close()

    def send_readings(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while self.running:
            if self.gateway_ip and self.gateway_udp_port and self.state == "LIGADO":
                reading = messages_pb2.DataReading()
                reading.source_id = SOURCE_ID
                reading.type = SOURCE_TYPE
                reading.value = self.intensidade
                reading.unit = "%"
                reading.timestamp = int(time.time())
                
                sock.sendto(b'\x02' + reading.SerializeToString(), (self.gateway_ip, self.gateway_udp_port))
            time.sleep(10)

    def run(self):
        threading.Thread(target=self.listen_for_discovery, daemon=True).start()
        threading.Thread(target=self.handle_tcp_control, daemon=True).start()
        threading.Thread(target=self.send_readings, daemon=True).start()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False
            print("Saindo...")

if __name__ == '__main__':
    src = PosteIluminacao()
    src.run()
