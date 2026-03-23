# Runbooks de Incidente (pós-go-live)

Prioridade operacional padrão deste pacote: **P2 (média)**.

## Catálogo

- `incident-availability.md`
- `incident-llm-timeout.md`
- `incident-prompt-bloat.md`
- `incident-rag-degradation.md`

## Fluxo padrão de resposta

1. Confirmar alerta no Prometheus/Grafana (evitar falso positivo).
2. Classificar impacto (staging/prod, escopo de usuários, degradação parcial/total).
3. Aplicar mitigação imediata do runbook específico.
4. Se necessário, executar rollback (canary/blue-green).
5. Registrar timeline e causa provável para ajuste de threshold/calibração.

## Referências rápidas

- Estado de release:
  - `python3 ops/deploy/deployctl.py print-state --env production`
- Rollback:
  - `make rollback-deploy ENV=production STRATEGY=auto`
- Saúde da API:
  - `GET /health`
  - `GET /api/v1/observability/metrics`
  - `GET /metrics`
