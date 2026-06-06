# Uso de Protobuf no Projeto

O **Protocol Buffers (Protobuf)**, desenvolvido pelo Google, é o mecanismo utilizado neste projeto para estruturar e serializar (transformar em bytes) todos os dados trafegados na rede. 
Diferente do JSON, o Protobuf não envia os dados em formato de texto estruturado. Ele compacta a mensagem em uma estrutura binária minúscula, que é incrivelmente rápida para ser transmitida e processada tanto por sistemas Python quanto Go.

Abaixo estão os recortes de código que provam como essa serialização e desserialização ocorrem em diferentes canais da nossa arquitetura.

---

## 1. O Contrato Principal (`proto/messages.proto`)
Antes de tudo, definimos nossas estruturas. O compilador do Protobuf (`protoc`) pega este arquivo e gera o código-fonte automaticamente para Python (`messages_pb2.py`) e Go (`pb/messages.pb.go`).

```proto
// Exemplo do contrato de telemetria
message DataReading {
    string source_id = 1;
    string type = 2;
    float value = 3;
    string unit = 4;
    int64 timestamp = 5;
}
```

---

## 2. Comunicação: Gateway ↔ Sensores (UDP)

### A. Gateway envia Requisição de Descoberta (Serialização)
No arquivo `gateway/main.py`, o coordenador cria um objeto Protobuf em memória, preenche seus dados e usa `.SerializeToString()` para convertê-lo em binário antes de disparar na rede Multicast.

```python
# gateway/main.py
req = messages_pb2.DiscoveryRequest()
req.gateway_ip = socket.gethostbyname(socket.gethostname())
req.gateway_udp_port = GATEWAY_UDP_PORT
req.gateway_tcp_port = GATEWAY_TCP_PORT

# Serializa o objeto protobuf para binário e anexa um byte prefixo (0x00)
msg = req.SerializeToString()
sock.sendto(b'\x00' + msg, (MULTICAST_GROUP, MULTICAST_PORT))
```

### B. Sensor de Temperatura recebe Descoberta (Desserialização)
O sensor intercepta o pacote UDP, retira o byte inicial e passa o array de bytes binário para `.ParseFromString()`. Os dados voltam a ser um objeto limpo com atributos legíveis.

```python
# sources/temperatura/main.py
data, addr = sock.recvfrom(4096)
msg_type = data[0]

if msg_type == 0: # DiscoveryRequest
    req = messages_pb2.DiscoveryRequest()
    # converte os bytes recebidos de volta para Objeto Python
    req.ParseFromString(data[1:])
    self.gateway_ip = req.gateway_ip
```

### C. O Semáforo em Golang enviando Telemetria (Serialização em Go)
Demonstrando a **heterogeneidade**, o nó escrito em Golang gera o pacote Protobuf usando o pacote oficial `google.golang.org/protobuf/proto`. Note que o modelo mental é idêntico: instanciar o objeto e usar `proto.Marshal()`.

```go
// sources/semaforo/main.go
reading := &pb.DataReading{
    SourceId:  SourceID,
    Type:      SourceType,
    Value:     float32(val),
    Unit:      "estado",
    Timestamp: time.Now().Unix(),
}

// proto.Marshal converte a struct Go em um array de bytes binário
out, err := proto.Marshal(reading)
if err == nil {
    // adiciona o byte de prefixo e envia via UDP
    msg := append([]byte{2}, out...)
    s.udpConn.WriteToUDP(msg, gatewayAddr)
}
```

---

## 3. Comunicação: Gateway ↔ Cliente Analítico (TCP)

Para consultas de listagens e envio de comandos manuais, o Cliente e o Gateway trocam pacotes via TCP fechado. O Protobuf brilha aqui pois garante que o *payload* da API fique minúsculo, poupando a conexão.

### A. Cliente solicita Histórico (Serialização)
No cliente CLI (`client/main.py`), uma requisição é criada, preenchida e despachada para a porta `5001`.

```python
# client/main.py
req = messages_pb2.ClientRequest()
req.type = messages_pb2.ClientRequest.GET_HISTORY
req.filter_type = "temperatura"

#serializa para rede TCP
req_data = req.SerializeToString()
# um cabeçalho de 4 bytes indicando o tamanho do payload é anexado (TCP padrão)
sock.sendall(struct.pack('>I', len(req_data)) + req_data)
```

### B. Gateway recebe e processa o Pedido (Desserialização)
O Gateway extrai o `payload` bruto do TCP e o repassa para a biblioteca Protobuf recriar o objeto de requisição.

```python
# gateway/main.py (handle_client_connection)
req = messages_pb2.ClientRequest()
req.ParseFromString(payload)

if req.type == messages_pb2.ClientRequest.GET_HISTORY:
    resp = messages_pb2.ClientResponse()
    resp.success = True
    
    # preenche a lista do Protobuf interativamente
    for r in hist_data:
        hr = resp.history.add()
        hr.source_id = r['source_id']
        hr.value = r['value']
        # ...
        
    #serializa a resposta montada de volta para binário
    resp_data = resp.SerializeToString()
    conn.sendall(struct.pack('>I', len(resp_data)) + resp_data)
```

---

