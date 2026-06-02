import socket
import struct
import time
import threading
import sys
import os
import random

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from proto import messages_pb2

SOURCE_ID = "sensor_temp_01"
SOURCE_TYPE = "temperatura"
MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = 5000

class SensorTemperatura:
    def __init__(self):
        self.gateway_ip = None
        self.gateway_udp_port = None
        self.running = True

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
            if msg_type == 0: # DiscoveryRequest
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
        resp.tcp_port = 0 # Não controlável
        resp.initial_state = "Ativo"
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(b'\x01' + resp.SerializeToString(), (self.gateway_ip, self.gateway_udp_port))
        sock.close()

    def send_readings(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while self.running:
            # Simulação de Falha: 10% de chance de o sensor "travar" por 20 segundos
            if SOURCE_ID == "sensor_temp_01" and random.random() < 0.10:
                print("[!] ERRO SIMULADO: Falha de hardware detectada. Sensor inoperante...")
                time.sleep(20)
                print("[+] RECUPERADO: O sensor reiniciou e voltou a operar.")

            if self.gateway_ip and self.gateway_udp_port:
                reading = messages_pb2.DataReading()
                reading.source_id = SOURCE_ID
                reading.type = SOURCE_TYPE
                reading.value = round(random.uniform(20.0, 35.0), 2)
                reading.unit = "Celsius"
                reading.timestamp = int(time.time())
                
                sock.sendto(b'\x02' + reading.SerializeToString(), (self.gateway_ip, self.gateway_udp_port))
                print(f"[>] Leitura enviada: {reading.value} {reading.unit}")
            time.sleep(5)

    def run(self):
        threading.Thread(target=self.listen_for_discovery, daemon=True).start()
        threading.Thread(target=self.send_readings, daemon=True).start()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False
            print("Saindo...")

if __name__ == '__main__':
    sensor = SensorTemperatura()
    sensor.run()
