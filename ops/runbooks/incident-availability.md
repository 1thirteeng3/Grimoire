# Incident Runbook: Queda de Disponibilidade (WS)

## Sinais

- Alertas:
  - `GrimoireAvailabilitySLOWarning`
  - `GrimoireAvailabilitySLOCritical`
- Aumento de desconexões WS, 1008 close codes, erro de pipeline

## Diagnóstico rápido

1. Verificar SLI:
   - `grimoire:sli:ws_availability:5m`
   - `grimoire:sli:ws_availability:30m`
2. Correlacionar com erros:
   - `grimoire_stage_errors_total{stage="WS"}`
   - `grimoire_errors_total{stage="WS",error_type=...}`
3. Identificar se causa é:
   - saturação
   - rate limiting agressivo
   - regressão de release

## Mitigação imediata (P2)

1. Se canary ativo, abortar/promover rollback canário imediatamente.
2. Se blue/green recente, rollback para slot anterior:
   - `make rollback-deploy ENV=production STRATEGY=auto`
3. Ajustar limites de taxa apenas como mitigação temporária e auditável.

## Critério de estabilização

- Disponibilidade >99.5% (30m) e >99.0% (5m) com tráfego representativo.
- Erros WS retornam ao patamar basal.

## Pós-incidente

- Revisar capacidade e autoscaling.
- Revalidar testes de carga no staging espelhado.
