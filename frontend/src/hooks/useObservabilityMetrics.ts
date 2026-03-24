import { useCallback, useEffect, useMemo, useState } from "react";

export interface StageMetrics {
  count: number;
  errors: number;
  avg_ms: number;
  max_ms: number;
}

export interface ObservabilityMetricsSnapshot {
  requests_total: number;
  stages: Record<string, StageMetrics>;
  tokens: Record<string, number>;
  errors: Record<string, number>;
  error_rates_over_ws: Record<string, number>;
}

export type EndpointHealth = "unknown" | "up" | "down";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const POLL_INTERVAL_MS = 2000;

export function useObservabilityMetrics() {
  const apiBaseUrl = useMemo(
    () => import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL,
    []
  );
  const bearerToken = useMemo(
    () => import.meta.env.VITE_API_BEARER_TOKEN ?? "",
    []
  );
  const jsonEndpoint = `${apiBaseUrl}/api/v1/observability/metrics`;
  const prometheusEndpoint = `${apiBaseUrl}/metrics`;

  const [snapshot, setSnapshot] = useState<ObservabilityMetricsSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const [prometheusHealth, setPrometheusHealth] = useState<EndpointHealth>("unknown");
  const [prometheusLastCheckedAt, setPrometheusLastCheckedAt] = useState<number | null>(null);

  const probePrometheus = useCallback(async () => {
    try {
      const response = await fetch(prometheusEndpoint, {
        headers: {
          Accept: "text/plain",
          ...(bearerToken ? { Authorization: `Bearer ${bearerToken}` } : {})
        }
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const body = await response.text();
      setPrometheusHealth(body.includes("grimoire_") ? "up" : "down");
    } catch {
      setPrometheusHealth("down");
    } finally {
      setPrometheusLastCheckedAt(Date.now());
    }
  }, [bearerToken, prometheusEndpoint]);

  const fetchSnapshot = useCallback(async () => {
    try {
      const response = await fetch(jsonEndpoint, {
        headers: {
          Accept: "application/json",
          ...(bearerToken ? { Authorization: `Bearer ${bearerToken}` } : {})
        }
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = (await response.json()) as ObservabilityMetricsSnapshot;
      setSnapshot(payload);
      setError(null);
      setLastUpdatedAt(Date.now());
    } catch (err) {
      const message = err instanceof Error ? err.message : "unknown error";
      setError(`Falha ao carregar metricas: ${message}`);
    } finally {
      setIsLoading(false);
    }
  }, [bearerToken, jsonEndpoint]);

  useEffect(() => {
    void fetchSnapshot();
    void probePrometheus();
    const interval = setInterval(() => {
      void fetchSnapshot();
      void probePrometheus();
    }, POLL_INTERVAL_MS);
    return () => {
      clearInterval(interval);
    };
  }, [fetchSnapshot, probePrometheus]);

  return {
    snapshot,
    isLoading,
    error,
    lastUpdatedAt,
    prometheusHealth,
    prometheusLastCheckedAt,
    jsonEndpoint,
    prometheusEndpoint
  };
}
