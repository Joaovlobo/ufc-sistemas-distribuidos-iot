package main

import (
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"semaforo/pb"
	"google.golang.org/protobuf/proto"
)

const (
	SourceID       = "semaforo_01"
	SourceType     = "semaforo"
	MulticastGroup = "224.1.1.1"
	MulticastPort  = 5000
	TCPPort        = 6004
)

type Semaforo struct {
	gatewayIP      string
	gatewayUDPPort int
	state          string
	cycleTime      int // seconds
	running        bool
}

func (s *Semaforo) getFullState() string {
	return fmt.Sprintf("%s | Ciclo: %ds", s.state, s.cycleTime)
}

func (s *Semaforo) listenForDiscovery() {
	addr, err := net.ResolveUDPAddr("udp", fmt.Sprintf("224.1.1.1:%d", MulticastPort))
	if err != nil {
		log.Fatalf("Erro ao resolver UDP addr: %v", err)
	}

	conn, err := net.ListenMulticastUDP("udp", nil, addr)
	if err != nil {
		log.Fatalf("Erro ao escutar Multicast: %v", err)
	}
	defer conn.Close()

	buf := make([]byte, 4096)
	log.Printf("[*] %s aguardando discovery do Gateway...", SourceID)

	for s.running {
		conn.SetReadDeadline(time.Now().Add(35 * time.Second))
		n, _, err := conn.ReadFromUDP(buf)
		if err != nil {
			if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
				if s.gatewayIP != "" {
					log.Println("[-] Gateway offline (timeout de discovery). Pausando envios...")
					s.gatewayIP = ""
					s.gatewayUDPPort = 0
				}
			} else {
				log.Printf("Erro na leitura UDP: %v", err)
			}
			continue
		}

		if n > 0 && buf[0] == 0 { // DiscoveryRequest
			req := &pb.DiscoveryRequest{}
			if err := proto.Unmarshal(buf[1:n], req); err != nil {
				log.Printf("Erro ao fazer parse do DiscoveryRequest: %v", err)
				continue
			}

			s.gatewayIP = req.GatewayIp
			s.gatewayUDPPort = int(req.GatewayUdpPort)
			log.Printf("[+] Gateway descoberto: %s:%d", s.gatewayIP, s.gatewayUDPPort)
			s.registerWithGateway()
			s.sendReading()
		}
	}
}

func getLocalIP() string {
	addrs, err := net.InterfaceAddrs()
	if err != nil {
		return "127.0.0.1"
	}
	for _, address := range addrs {
		if ipnet, ok := address.(*net.IPNet); ok && !ipnet.IP.IsLoopback() {
			if ipnet.IP.To4() != nil {
				return ipnet.IP.String()
			}
		}
	}
	return "127.0.0.1"
}

func (s *Semaforo) registerWithGateway() {
	resp := &pb.DiscoveryResponse{
		SourceId:     SourceID,
		Type:         SourceType,
		Ip:           getLocalIP(),
		TcpPort:      int32(TCPPort),
		InitialState: s.getFullState(),
	}

	out, err := proto.Marshal(resp)
	if err != nil {
		log.Printf("Erro ao marshal DiscoveryResponse: %v", err)
		return
	}

	addr, err := net.ResolveUDPAddr("udp", fmt.Sprintf("%s:%d", s.gatewayIP, s.gatewayUDPPort))
	if err != nil {
		return
	}

	conn, err := net.DialUDP("udp", nil, addr)
	if err != nil {
		return
	}
	defer conn.Close()

	payload := append([]byte{1}, out...)
	conn.Write(payload)
}

func (s *Semaforo) sendReading() {
	if s.gatewayIP == "" {
		return
	}

	val := 0.0
	if s.state == "verde" {
		val = 1.0
	} else if s.state == "amarelo" {
		val = 2.0
	} else if s.state == "vermelho" {
		val = 3.0
	}

	reading := &pb.DataReading{
		SourceId:  SourceID,
		Type:      SourceType,
		Value:     val,
		Unit:      "state",
		Timestamp: time.Now().Unix(),
	}

	out, err := proto.Marshal(reading)
	if err != nil {
		log.Printf("Erro ao marshal DataReading: %v", err)
		return
	}

	addr, err := net.ResolveUDPAddr("udp", fmt.Sprintf("%s:%d", s.gatewayIP, s.gatewayUDPPort))
	if err != nil {
		return
	}

	conn, err := net.DialUDP("udp", nil, addr)
	if err != nil {
		return
	}
	defer conn.Close()

	payload := append([]byte{2}, out...)
	conn.Write(payload)
}

func (s *Semaforo) handleTCPControl() {
	addr := fmt.Sprintf("0.0.0.0:%d", TCPPort)
	listener, err := net.Listen("tcp", addr)
	if err != nil {
		log.Fatalf("Erro ao ouvir TCP: %v", err)
	}
	defer listener.Close()
	log.Printf("[*] %s ouvindo comandos TCP na porta %d", SourceID, TCPPort)

	for s.running {
		conn, err := listener.Accept()
		if err != nil {
			continue
		}
		go s.processTCPConnection(conn)
	}
}

func (s *Semaforo) processTCPConnection(conn net.Conn) {
	defer conn.Close()
	buf := make([]byte, 1024)
	n, err := conn.Read(buf)
	if err != nil || n == 0 {
		return
	}

	cmd := &pb.ControlCommand{}
	if err := proto.Unmarshal(buf[:n], cmd); err != nil {
		return
	}

	log.Printf("[<] Comando recebido: %s %s", cmd.Command, cmd.Parameter)

	resp := &pb.ControlResponse{
		SourceId: SourceID,
		Success:  true,
	}

	if cmd.Command == "SET_STATE" {
		s.state = cmd.Parameter
		resp.Message = fmt.Sprintf("Semáforo alterado para %s.", s.state)
	} else if cmd.Command == "SET_CYCLE" {
		cycle, err := strconv.Atoi(cmd.Parameter)
		if err != nil {
			resp.Success = false
			resp.Message = "Tempo de ciclo inválido."
		} else {
			s.cycleTime = cycle
			resp.Message = fmt.Sprintf("Tempo de ciclo alterado para %ds.", s.cycleTime)
		}
	} else {
		resp.Success = false
		resp.Message = "Comando desconhecido."
	}

	if resp.Success {
		log.Printf("[*] Novo estado: %s", s.getFullState())
		if s.gatewayIP != "" {
			s.registerWithGateway()
			s.sendReading()
		}
	}

	out, _ := proto.Marshal(resp)
	conn.Write(out)
}

func (s *Semaforo) runSemaphores() {
	for s.running {
		if s.cycleTime > 0 {
			if s.state == "verde" {
				time.Sleep(time.Duration(s.cycleTime) * time.Second)
				s.state = "amarelo"
			} else if s.state == "amarelo" {
				time.Sleep(time.Duration(2) * time.Second)
				s.state = "vermelho"
			} else { // vermelho
				time.Sleep(time.Duration(s.cycleTime) * time.Second)
				s.state = "verde"
			}
			
			// send reading (state update)
			if s.gatewayIP != "" {
				s.registerWithGateway() // registrar updates state no gateway
				s.sendReading()         // send telemetry para dashboard 
			}
		} else {
			time.Sleep(2 * time.Second)
		}
	}
}

func main() {
	s := &Semaforo{
		state:     "verde",
		cycleTime: 10,
		running:   true,
	}

	go s.listenForDiscovery()
	go s.handleTCPControl()
	go s.runSemaphores()

	c := make(chan os.Signal, 1)
	signal.Notify(c, os.Interrupt, syscall.SIGTERM)
	<-c

	s.running = false
	log.Println("Saindo...")
}
