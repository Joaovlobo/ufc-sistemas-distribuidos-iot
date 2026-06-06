import socket
import struct
import time
import threading
import sys
import os
import random

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from proto import messages_pb2

SOURCE_ID = "sensor_ar_01"
SOURCE_TYPE = "qualidade_ar"
MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = 5000
TCP_PORT = 6003

class SensorAr:
    def __init__(self):
        self.gateway_ip = None
        self.gateway_udp_port = None
        self.running = True
        self.limiar_alerta = 1400 # ppm de CO2
        self.freq = 5 # segundos

    def get_full_state(self):
        return f"Ativo | Limiar: {self.limiar_alerta}ppm | Freq: {self.freq}s"

    def listen_for_discovery(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', MULTICAST_PORT))
        mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        sock.settimeout(35.0)

        print(f"[*] {SOURCE_ID} aguardando discovery do Gateway...")
        while self.running:
            try:
                data, addr = sock.recvfrom(4096)
                msg_type = data[0]
                if msg_type == 0:
                    req = messages_pb2.DiscoveryRequest()
                    req.ParseFromString(data[1:])
                    self.gateway_ip = req.gateway_ip
                    self.gateway_udp_port = req.gateway_udp_port
                    print(f"[+] Gateway descoberto: {self.gateway_ip}:{self.gateway_udp_port}")
                    self.register_with_gateway()
            except socket.timeout:
                if self.gateway_ip is not None:
                    print(f"[-] Gateway offline (timeout de discovery). Pausando envios...")
                    self.gateway_ip = None
                    self.gateway_udp_port = None

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
                
                if cmd.command == "SET_LIMIAR":
                    try:
                        self.limiar_alerta = int(cmd.parameter)
                        resp.message = f"Limiar ajustado para {self.limiar_alerta}ppm."
                    except ValueError:
                        resp.success = False
                        resp.message = "Parâmetro de limiar inválido."
                elif cmd.command == "SET_FREQ":
                    try:
                        self.freq = int(cmd.parameter)
                        resp.message = f"Frequência alterada para {self.freq}s."
                    except ValueError:
                        resp.success = False
                        resp.message = "Parâmetro de frequência inválido."
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
            # Simulação de Falha: 5% de chance de o sensor "travar" por 20 segundos
            if random.random() < 0.05:
                print("[!] ERRO SIMULADO: Falha de hardware detectada. Sensor de ar inoperante...")
                time.sleep(20)
                print("[+] RECUPERADO: O sensor de ar reiniciou e voltou a operar.")

            if self.gateway_ip and self.gateway_udp_port:
                reading = messages_pb2.DataReading()
                reading.source_id = SOURCE_ID
                reading.type = SOURCE_TYPE
                val = random.uniform(400, 1500)
                reading.value = round(val, 2)
                reading.unit = "ppm"
                reading.timestamp = int(time.time())
                
                sock.sendto(b'\x02' + reading.SerializeToString(), (self.gateway_ip, self.gateway_udp_port))
                
                if val > self.limiar_alerta:
                    print(f"[!] ALERTA: Qualidade do ar ruim ({val:.2f} ppm > {self.limiar_alerta})")
                else:
                    print(f"[>] Leitura enviada: {val:.2f} ppm")
            time.sleep(self.freq)

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
    src = SensorAr()
    src.run()
