# Incident Runbook: LLM Provider Timeout

## Sinais

- Alertas:
  - `GrimoireLLMProviderTimeoutHigh`
  - `GrimoireLLMAverageLatencyHigh`
- Sintomas de produto:
  - respostas incompletas no stream
  - aumento de latência no estágio LLM

## Diagnóstico rápido

1. Verificar métricas:
   - `grimoire_errors_total{stage="LLM",error_type="LLM_PROVIDER_TIMEOUT"}`
   - `grimoire:sli:llm_avg_latency_ms:5m`
2. Verificar logs estruturados:
   - `event=error_counter stage=LLM`
3. Confirmar se há degradação externa do provedor.

## Mitigação imediata (P2)

1. Reduzir carga concorrente no fluxo LLM (limitar bursts no cliente/ingress).
2. Ajustar temporariamente:
   - `GRIMOIRE_LLM_RETRY_MAX_ATTEMPTS`
   - `GRIMOIRE_LLM_RETRY_MAX_BACKOFF_SECONDS`
3. Se degradar severamente, executar rollback de release:
   - `make rollback-deploy ENV=production STRATEGY=auto`

## Critério de estabilização

- Timeout rate retorna para baseline + margem (<2x 24h baseline).
- Latência média LLM abaixo de threshold efetivo por >=30 minutos.

## Pós-incidente

- Registrar janela de falha, impacto e versão ativa.
- Recalibrar threshold caso padrão de tráfego tenha mudado.
