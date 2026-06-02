import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart, ReferenceLine, ReferenceArea } from 'recharts';
import { Activity, Radio, LayoutDashboard, Settings2, Clock } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

function App() {
  const [sources, setSources] = useState([]);
  const [historyData, setHistoryData] = useState([]);
  const [types, setTypes] = useState([]);
  const [filterType, setFilterType] = useState('qualidade_ar');
  const [viewLimit, setViewLimit] = useState(0); // 0 = All, 10 = Last 10
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      // Fetch Sources
      const srcRes = await fetch(`${API_BASE}/sources`);
      const srcJson = await srcRes.json();
      let activeSources = [];
      if (srcJson.success) {
        setSources(srcJson.sources);
        activeSources = srcJson.sources.map(s => s.type);
      }

      // Fetch Types
      const typesRes = await fetch(`${API_BASE}/types`);
      const typesJson = await typesRes.json();
      if (typesJson.success) {
        const combinedTypes = Array.from(new Set([...typesJson.types, ...activeSources]));
        setTypes(combinedTypes);
        if (!combinedTypes.includes(filterType) && filterType === '') {
          if (combinedTypes.length > 0) setFilterType(combinedTypes[0]);
        }
      }

      // Fetch History
      const histRes = await fetch(`${API_BASE}/history?filter_type=${filterType}&limit=${viewLimit}`);
      const histJson = await histRes.json();
      if (histJson.success) {
          const formatted = histJson.data.map(d => {
           const date = new Date(d.timestamp * 1000);
           return {
             ...d,
             timeStr: `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`,
             value: d.unit === 'OFFLINE' ? null : d.value
           }
        });
        setHistoryData(formatted);
      }
      setLoading(false);
    } catch (e) {
      console.error(e);
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000); // refresh every 3s
    return () => clearInterval(interval);
  }, [filterType, viewLimit]);

  const handleCommand = async (source_id, command, parameter) => {
    try {
      const res = await fetch(`${API_BASE}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_id, command, parameter })
      });
      const json = await res.json();
      if (json.success) {
        fetchData(); // refresh immediately
      } else {
        alert(json.detail);
      }
    } catch (e) {
      alert('Failed to send command');
    }
  };

  const getMetricSummary = () => {
    if (!historyData || historyData.length === 0) return { avg: 0, min: 0, max: 0, activeTime: 0, airStats: null, failPercent: "0.0" };
    
    const validData = historyData.filter(d => d.value !== null);
    const values = validData.map(d => d.value);
    
    const avg = values.length > 0 ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(2) : 0;
    const min = values.length > 0 ? Math.min(...values).toFixed(2) : 0;
    const max = values.length > 0 ? Math.max(...values).toFixed(2) : 0;
    
    let activeTime = 0;
    let activeLabel = 'Active Events';
    let airStats = null;
    
    if (filterType === 'poste_iluminacao') {
       activeTime = historyData.filter(d => d.value > 0).length * 10;
       activeLabel = 'Time Active (s)';
    } else if (filterType === 'camera') {
       activeTime = historyData.length;
       activeLabel = 'Frames Captured';
    } else if (filterType === 'qualidade_ar') {
       activeTime = historyData.filter(d => d.value > 1400).length;
       activeLabel = 'Alerts (>1400ppm)';
       
       const total = historyData.length;
       if (total > 0) {
         airStats = {
           fresco: ((historyData.filter(d => d.value <= 400).length / total) * 100).toFixed(1),
           normal: ((historyData.filter(d => d.value > 400 && d.value <= 1000).length / total) * 100).toFixed(1),
           ruim: ((historyData.filter(d => d.value > 1000 && d.value <= 1400).length / total) * 100).toFixed(1),
           alta: ((historyData.filter(d => d.value > 1400).length / total) * 100).toFixed(1),
         };
       }
    } else if (filterType === 'semaforo') {
       activeTime = historyData.length;
       activeLabel = 'State Changes';
    } else if (filterType === 'temperatura') {
       activeTime = historyData.filter(d => d.value > 30 && d.unit !== 'OFFLINE').length;
       activeLabel = 'Hot Events (>30C)';
    }
    
    // Calcula Taxa de Falha
    const totalPoints = historyData.length;
    const offlinePoints = historyData.filter(d => d.unit === 'OFFLINE').length;
    const failPercent = totalPoints > 0 ? ((offlinePoints / totalPoints) * 100).toFixed(1) : "0.0";
    
    return { avg, min, max, activeTime, activeLabel, airStats, failPercent };
  };

  const summary = getMetricSummary();

  const formatTooltip = (value, name, props) => {
    if (filterType === 'semaforo') {
      if (value === 1) return ['Verde', 'Status'];
      if (value === 2) return ['Amarelo', 'Status'];
      if (value === 3) return ['Vermelho', 'Status'];
    }
    return [value, 'Value'];
  };

  const formatYAxis = (value) => {
    if (filterType === 'semaforo') {
      if (value === 1) return 'Verde';
      if (value === 2) return 'Amarelo';
      if (value === 3) return 'Vermel.';
      return '';
    }
    return value;
  };

  return (
    <div className="dashboard-container">
      <header className="header">
        <h1><LayoutDashboard className="header-icon" /> Smart City Control Panel</h1>
      </header>

      <div className="grid-layout">
        
        {/* Left Sidebar: Sources List */}
        <div className="glass-panel">
          <div className="top-bar">
            <h2><Radio size={20} style={{marginRight: '8px', verticalAlign: 'middle'}}/> Connected Nodes</h2>
          </div>
          <div className="sources-list">
            {sources.length === 0 && <p className="text-secondary">No sources connected.</p>}
            
            {[...sources].sort((a, b) => a.type === 'semaforo' ? 1 : b.type === 'semaforo' ? -1 : 0).map(s => {
              const stateStr = s.state.toUpperCase();
              const isLIGADO = stateStr.startsWith('LIGADO');
              const isDESLIGADO = stateStr.startsWith('DESLIGADO');
              
              return (
                <div 
                  key={s.id} 
                  className={`source-card ${filterType === s.type ? 'selected-card' : ''}`}
                  onClick={() => setFilterType(s.type)}
                >
                  <div className="source-header">
                    <span className="source-title">{s.id}</span>
                    <div className="status-badge active">
                      <span className="status-dot"></span> Online
                    </div>
                  </div>
                  <div className="source-type">{s.type}</div>
                  <div className="text-secondary" style={{fontSize: '0.85rem', marginTop: '0.5rem', wordBreak: 'break-all'}}>
                    State: {s.state}
                  </div>
                  
                  {/* Dynamic Controls based on type */}
                  {s.type === 'camera' && (
                    <div className="control-actions" onClick={e => e.stopPropagation()}>
                      <button className={`btn ${isLIGADO ? 'btn-active' : ''}`} onClick={() => handleCommand(s.id, 'LIGAR', '')}>ON</button>
                      <button className={`btn ${isDESLIGADO ? 'btn-active' : ''}`} onClick={() => handleCommand(s.id, 'DESLIGAR', '')}>OFF</button>
                    </div>
                  )}
                  {s.type === 'poste_iluminacao' && (
                    <div className="control-actions" onClick={e => e.stopPropagation()}>
                      <button className={`btn ${isLIGADO ? 'btn-active' : ''}`} onClick={() => handleCommand(s.id, 'LIGAR', '')}>ON</button>
                      <button className={`btn ${isDESLIGADO ? 'btn-active' : ''}`} onClick={() => handleCommand(s.id, 'DESLIGAR', '')}>OFF</button>
                      <button className={`btn ${stateStr.includes('50%') ? 'btn-active' : ''}`} onClick={() => handleCommand(s.id, 'SET_INTENSITY', '50')}>50%</button>
                      <button className={`btn ${stateStr.includes('100%') ? 'btn-active' : ''}`} onClick={() => handleCommand(s.id, 'SET_INTENSITY', '100')}>100%</button>
                    </div>
                  )}
                  {s.type === 'semaforo' && (
                    <div className="control-actions" onClick={e => e.stopPropagation()}>
                      <button className={`btn ${stateStr.includes('VERDE') ? 'btn-active' : ''}`} onClick={() => handleCommand(s.id, 'SET_STATE', 'verde')}>Green</button>
                      <button className={`btn ${stateStr.includes('AMARELO') ? 'btn-active' : ''}`} onClick={() => handleCommand(s.id, 'SET_STATE', 'amarelo')}>Yellow</button>
                      <button className={`btn ${stateStr.includes('VERMELHO') ? 'btn-active' : ''}`} onClick={() => handleCommand(s.id, 'SET_STATE', 'vermelho')}>Red</button>
                    </div>
                  )}
                  {/* qualidade_ar controls removed to lock threshold at 1000ppm */}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Content: Analytics */}
        <div className="glass-panel" style={{display: 'flex', flexDirection: 'column'}}>
          <div className="top-bar">
            <h2><Activity size={20} style={{marginRight: '8px', verticalAlign: 'middle', color: 'var(--accent-blue)'}}/> Live Analytics</h2>
            <div className="filter-group">
              <Settings2 size={18} color="var(--text-secondary)" />
              <select 
                className="select-input" 
                value={filterType} 
                onChange={(e) => setFilterType(e.target.value)}
              >
                {types.map(t => {
                  const sourceId = sources.find(s => s.type === t)?.id || t;
                  return <option key={t} value={t}>{sourceId.toUpperCase()}</option>;
                })}
                {types.length === 0 && <option value="">No data yet</option>}
              </select>
              
              <Clock size={18} color="var(--text-secondary)" style={{marginLeft: '0.5rem'}}/>
              <select 
                className="select-input" 
                value={viewLimit} 
                onChange={(e) => setViewLimit(Number(e.target.value))}
              >
                <option value={0}>All Data</option>
                <option value={10}>Last 10 Records</option>
                <option value={50}>Last 50 Records</option>
              </select>
            </div>
          </div>

          {loading && historyData.length === 0 ? (
            <div className="loading-overlay">Loading data...</div>
          ) : (
            <>
              <div className="metrics-grid">
                <div className="metric-card">
                  <span className="metric-title">Average Value</span>
                  <span className="metric-value" style={{color: 'var(--accent-blue)'}}>{summary.avg}</span>
                </div>
                <div className="metric-card">
                  <span className="metric-title">Minimum</span>
                  <span className="metric-value">{summary.min}</span>
                </div>
                <div className="metric-card">
                  <span className="metric-title">Maximum</span>
                  <span className="metric-value">{summary.max}</span>
                </div>
                <div className="metric-card">
                  <span className="metric-title">{summary.activeLabel}</span>
                  <span className="metric-value" style={{color: 'var(--accent-yellow)'}}>{summary.activeTime}</span>
                </div>
                <div className="metric-card">
                  <span className="metric-title">Taxa de Falhas (Uptime)</span>
                  <span className="metric-value" style={{color: summary.failPercent > 0 ? 'var(--accent-red)' : 'var(--accent-green)'}}>{summary.failPercent}%</span>
                </div>
              </div>
              
              {filterType === 'qualidade_ar' && summary.airStats && (
                <div className="air-percentages">
                  <div className="air-percent-badge" style={{borderLeftColor: 'var(--accent-green)'}}>
                    <span className="metric-title">Fresco (≤400)</span>
                    <span style={{fontSize: '1.25rem', fontWeight: 600}}>{summary.airStats.fresco}%</span>
                  </div>
                  <div className="air-percent-badge" style={{borderLeftColor: 'var(--accent-blue)'}}>
                    <span className="metric-title">Normal (401-1000)</span>
                    <span style={{fontSize: '1.25rem', fontWeight: 600}}>{summary.airStats.normal}%</span>
                  </div>
                  <div className="air-percent-badge" style={{borderLeftColor: 'var(--accent-yellow)'}}>
                    <span className="metric-title">Ruim (1001-1400)</span>
                    <span style={{fontSize: '1.25rem', fontWeight: 600}}>{summary.airStats.ruim}%</span>
                  </div>
                  <div className="air-percent-badge" style={{borderLeftColor: 'var(--accent-red)'}}>
                    <span className="metric-title">Alta (acima1400)</span>
                    <span style={{fontSize: '1.25rem', fontWeight: 600}}>{summary.airStats.alta}%</span>
                  </div>
                </div>
              )}

              <div className="chart-container" style={{flex: 1, marginTop: '1rem'}}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={historyData} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="normalColor" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--accent-blue)" stopOpacity={0.4}/>
                        <stop offset="95%" stopColor="var(--accent-blue)" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                    <XAxis 
                      dataKey="timeStr" 
                      stroke="var(--text-secondary)" 
                      tick={{fill: 'var(--text-secondary)', fontSize: 12}}
                      tickLine={false}
                      axisLine={false}
                      minTickGap={30}
                    />
                    <YAxis 
                      stroke="var(--text-secondary)"
                      tick={{fill: 'var(--text-secondary)', fontSize: 12}}
                      tickFormatter={formatYAxis}
                      tickLine={false}
                      axisLine={false}
                      domain={['auto', 'auto']}
                    />
                    <Tooltip 
                      formatter={formatTooltip}
                      contentStyle={{backgroundColor: 'rgba(15, 23, 42, 0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px'}}
                      itemStyle={{color: 'var(--text-primary)'}}
                    />

                    {filterType === 'qualidade_ar' && (
                      <>
                        <ReferenceArea y2={400} fill="var(--accent-green)" fillOpacity={0.08} />
                        <ReferenceArea y1={400} y2={1000} fill="var(--accent-blue)" fillOpacity={0.03} />
                        <ReferenceArea y1={1000} y2={1400} fill="var(--accent-yellow)" fillOpacity={0.08} />
                        <ReferenceArea y1={1400} fill="var(--accent-red)" fillOpacity={0.08} />
                      </>
                    )}

                    {filterType === 'semaforo' && (
                      <>
                        <ReferenceArea y1={0.5} y2={1.5} fill="var(--accent-green)" fillOpacity={0.08} />
                        <ReferenceArea y1={1.5} y2={2.5} fill="var(--accent-yellow)" fillOpacity={0.08} />
                        <ReferenceArea y1={2.5} y2={3.5} fill="var(--accent-red)" fillOpacity={0.08} />
                      </>
                    )}

                    <Area 
                      type={filterType === 'semaforo' || filterType === 'poste_iluminacao' ? "stepAfter" : "monotone"} 
                      dataKey="value" 
                      stroke="var(--accent-blue)"
                      strokeWidth={3}
                      fillOpacity={1} 
                      fill="url(#normalColor)"
                      isAnimationActive={false} 
                      connectNulls={false}
                    />
                    
                    {filterType === 'qualidade_ar' && (
                      <>
                        <ReferenceLine y={400} stroke="rgba(255,255,255,0.2)" strokeDasharray="3 3" />
                        <ReferenceLine y={1000} stroke="rgba(255,255,255,0.2)" strokeDasharray="3 3" />
                        <ReferenceLine y={1400} stroke="var(--accent-red)" strokeDasharray="3 3" />
                      </>
                    )}

                    {filterType === 'temperatura' && (
                      <ReferenceLine 
                        y={30} 
                        stroke="var(--accent-red)" 
                        strokeDasharray="5 5" 
                        strokeWidth={2}
                        label={{ position: 'insideBottomLeft', value: '30°C Threshold', fill: 'var(--accent-red)', fontSize: 13, fontWeight: 600, offset: 10 }} 
                      />
                    )}
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </div>

      </div>
    </div>
  );
}

export default App;
