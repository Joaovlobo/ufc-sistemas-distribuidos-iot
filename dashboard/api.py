from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import socket
import struct
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from proto import messages_pb2

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GATEWAY_IP = os.getenv('GATEWAY_IP', '127.0.0.1')
GATEWAY_TCP_PORT = 5001
CSV_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'dados_gateway.csv')

class CommandRequest(BaseModel):
    source_id: str
    command: str
    parameter: str = ""

def send_to_gateway(req: messages_pb2.ClientRequest) -> messages_pb2.ClientResponse:
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
        print(f"Error connecting to Gateway: {e}")
        return None

@app.get("/api/sources")
def get_sources():
    req = messages_pb2.ClientRequest()
    req.type = messages_pb2.ClientRequest.LIST_SOURCES
    resp = send_to_gateway(req)
    if not resp or not resp.success:
        raise HTTPException(status_code=500, detail="Failed to connect to Gateway or retrieve sources.")
        
    sources = []
    for s in resp.sources:
        sources.append({
            "id": s.source_id,
            "type": s.type,
            "state": s.state
        })
    return {"success": True, "sources": sources}

@app.post("/api/command")
def send_command(cmd: CommandRequest):
    req = messages_pb2.ClientRequest()
    req.type = messages_pb2.ClientRequest.CONTROL_COMMAND
    req.control_command.source_id = cmd.source_id
    req.control_command.command = cmd.command
    req.control_command.parameter = cmd.parameter
    
    resp = send_to_gateway(req)
    if not resp:
        raise HTTPException(status_code=500, detail="Failed to connect to Gateway.")
        
    if not resp.success:
        raise HTTPException(status_code=400, detail=resp.message)
        
    return {"success": True, "message": resp.message}

@app.get("/api/history")
def get_history(filter_type: str = "", limit: int = 0):
    if not os.path.exists(CSV_FILE):
        return {"success": True, "data": []}
    
    try:
        df = pd.read_csv(CSV_FILE)
        if df.empty:
            return {"success": True, "data": []}
            
        if filter_type:
            df = df[df['type'] == filter_type]
            
        if limit > 0:
            df = df.tail(limit)
        else:
            df = df.tail(1000) # Fallback to last 1000 to prevent crash if huge
        
        data = df.to_dict(orient='records')
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read data: {str(e)}")

@app.get("/api/types")
def get_types():
    # Returns unique source types from CSV for the filter dropdown
    if not os.path.exists(CSV_FILE):
        return {"success": True, "types": []}
    try:
        df = pd.read_csv(CSV_FILE)
        if df.empty:
            return {"success": True, "types": []}
        types = df['type'].unique().tolist()
        return {"success": True, "types": types}
    except Exception as e:
        return {"success": False, "types": []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
