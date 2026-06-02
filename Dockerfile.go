FROM golang:1.23-alpine AS builder

WORKDIR /app

# Instalar protoc e o plugin do Go para protobuf
RUN apk add --no-cache protoc
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@latest

# Copia o protobuf e os fontes do semaforo
COPY proto/ /app/proto/
COPY sources/semaforo/ /app/sources/semaforo/

WORKDIR /app/sources/semaforo
# Gera o código do protobuf em go (criará a pasta pb internamente)
RUN protoc -I=../../proto --go_out=. ../../proto/messages.proto
RUN go mod tidy
RUN go build -o /semaforo_bin main.go

FROM alpine:latest
WORKDIR /app
COPY --from=builder /semaforo_bin /app/semaforo_bin

CMD ["/app/semaforo_bin"]
