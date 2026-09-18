# Changelog

Todas as mudanças notáveis nos agentes, skills e scripts deste framework ficam registradas
aqui. Formato baseado em [Keep a Changelog](https://keepachangelog.com/), versionamento
[semver](https://semver.org/): MAJOR.MINOR.PATCH — MAJOR para mudança que quebra projetos já
em andamento (ex: campo renomeado, contrato de `decide.py` alterado), MINOR para agente/skill
novo ou capacidade nova sem quebrar nada existente, PATCH para correção de bug.

Ao aplicar uma proposta de melhoria vinda da skill `/auditoria-arquitetura` (ou qualquer outra
mudança manual), quem aplica é responsável por: incrementar `VERSION` e acrescentar uma entrada
aqui, no mesmo commit. Sem isso, `atualizar.sh` não tem o que reportar ao rodar em outra
máquina.

## [1.0.0] — 2026-09-18

Primeira versão com controle de versão formal. Consolida todas as correções da auditoria de
18/09/2026:

- Planner e llm-qualification ganharam `Edit` nas tools e regra explícita de preservar
  entradas existentes em arquivo compartilhado (`backlog.md`, `prompt-tests.md`) — corrige
  risco de perda de dados por `Write` cego.
- `decide.py`: `gatilho_tarefa_travada` deixou de gravar estado a cada chamada — agora é
  leitura pura, conforme a docstring do módulo já prometia. O incremento de
  `ciclos_sem_progresso` passou para o Implementador.
- `CLAUDE.md.template`: referência a `.claude/agents/` corrigida para deixar explícito que é
  nível de usuário (`~/.claude/agents/`), com instrução de rodar `setup-machine.sh` se ausente.
- Estrutura do pacote simplificada: eliminada a duplicação entre `.claude/agents/` e
  `deploy/framework/agents/` — agora existe uma única árvore versionada.
