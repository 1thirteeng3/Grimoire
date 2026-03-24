import "./App.css";

import { useMemo } from "react";

import { useObservabilityMetrics, type StageMetrics } from "./hooks/useObservabilityMetrics";
import { useWebSocket } from "./hooks/useWebSocket";
import { useSystemStore } from "./store/system";

export default function App() {
  const { fsmState, isConnected, confidenceState, activePactId, streamBuffer } = useSystemStore();
  const {
    snapshot,
    isLoading,
    error,
    lastUpdatedAt,
    prometheusHealth,
    prometheusLastCheckedAt,
    jsonEndpoint,
    prometheusEndpoint
  } = useObservabilityMetrics();

  useWebSocket("frontend_observability_panel");

  const stages: Array<{ name: "WS" | "RAG" | "LLM"; metrics: StageMetrics | null }> = useMemo(
    () => [
      { name: "WS", metrics: snapshot?.stages.WS ?? null },
      { name: "RAG", metrics: snapshot?.stages.RAG ?? null },
      { name: "LLM", metrics: snapshot?.stages.LLM ?? null }
    ],
    [snapshot]
  );

  const tokenInput = snapshot?.tokens.input ?? 0;
  const tokenOutput = snapshot?.tokens.output ?? 0;

  const errorRows = useMemo(
    () =>
      Object.entries(snapshot?.errors ?? {})
        .sort((a, b) => b[1] - a[1])
        .map(([key, count]) => {
          const rate = snapshot?.error_rates_over_ws[key] ?? 0;
          return { key, count, rate };
        }),
    [snapshot]
  );

  return (
    <main className="app-shell">
      <header className="app-header">
        <h1>Grimoire - Observability Panel</h1>
        <p className="muted">
          Atualizacao em tempo real por polling do endpoint JSON e link para export Prometheus.
        </p>
      </header>

      <section className="status-row">
        <span className="status-chip">FSM: {fsmState}</span>
        <span className="status-chip">WS: {isConnected ? "connected" : "disconnected"}</span>
        <span className="status-chip">Confidence: {confidenceState ?? "n/a"}</span>
        <span className="status-chip">Pact: {activePactId ?? "none"}</span>
        <span className="status-chip">WS requests total: {snapshot?.requests_total ?? 0}</span>
      </section>

      <section>
        <h2 className="section-title">Latencia por etapa</h2>
        <div className="grid grid-3">
          {stages.map(({ name, metrics }) => (
            <article className="card" key={name}>
              <h3>{name}</h3>
              <p className="metric-line">count: {metrics?.count ?? 0}</p>
              <p className="metric-line">errors: {metrics?.errors ?? 0}</p>
              <p className="metric-line">avg ms: {metrics?.avg_ms ?? 0}</p>
              <p className="metric-line">max ms: {metrics?.max_ms ?? 0}</p>
            </article>
          ))}
        </div>
      </section>

      <section>
        <h2 className="section-title">Tokens</h2>
        <div className="grid grid-2">
          <article className="card">
            <h3>Input tokens</h3>
            <p className="metric-line">{tokenInput}</p>
          </article>
          <article className="card">
            <h3>Output tokens</h3>
            <p className="metric-line">{tokenOutput}</p>
          </article>
        </div>
      </section>

      <section>
        <h2 className="section-title">Taxa de erro por tipo</h2>
        <article className="card">
          {errorRows.length === 0 ? (
            <p className="metric-line">Sem erros registrados.</p>
          ) : (
            <table className="error-table">
              <thead>
                <tr>
                  <th>error key</th>
                  <th>count</th>
                  <th>rate over ws</th>
                </tr>
              </thead>
              <tbody>
                {errorRows.map((row) => (
                  <tr key={row.key}>
                    <td>{row.key}</td>
                    <td>{row.count}</td>
                    <td>{row.rate.toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </article>
      </section>

      <section>
        <h2 className="section-title">Endpoints</h2>
        <p className="metric-line">
          Prometheus (opcional):{" "}
          <span className={`health-chip health-${prometheusHealth}`}>
            {prometheusHealth.toUpperCase()}
          </span>
          {prometheusLastCheckedAt ? (
            <span className="muted">
              {" "}
              (checado {new Date(prometheusLastCheckedAt).toLocaleTimeString()})
            </span>
          ) : null}
        </p>
        <div className="endpoint-links">
          <a href={jsonEndpoint} target="_blank" rel="noreferrer">
            JSON metrics
          </a>
          <a href={prometheusEndpoint} target="_blank" rel="noreferrer">
            Prometheus /metrics
          </a>
        </div>
      </section>

      <section>
        <h2 className="section-title">Status do painel</h2>
        {isLoading && <p className="metric-line">Carregando metricas...</p>}
        {error && <p className="metric-line error-text">{error}</p>}
        <p className="muted">
          Ultima atualizacao:{" "}
          {lastUpdatedAt ? new Date(lastUpdatedAt).toLocaleTimeString() : "sem amostra"}
        </p>
      </section>

      <section className="stream-preview">
        <strong>Stream preview:</strong>
        {"\n"}
        {streamBuffer || "[sem tokens stream]"}
      </section>
    </main>
  );
}
