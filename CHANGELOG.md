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

## [1.0.1] — 2026-09-18

Correção de dois bugs de roteamento em `decide.py`. Ambos reproduzidos em projeto sintético
antes da correção; suíte de regressão adicionada em `tests/test_decide.py` (16 casos).

- `gatilho_spec_ausente` disparava para QUALQUER spec referenciada e inexistente. Como os
  gatilhos são avaliados antes de `mapear_tarefa_para_agente()`, ele interceptava o estado
  normal de uma tarefa recém-criada — o Planner lista `docs/specs/design/<componente>.md` em
  `specs_referenciadas` justamente porque a spec ainda não existe. Consequências: todo o
  despacho para especialista era código inalcançável (os agentes `planner`, `design`,
  `data-pipeline` e `llm-qualification` só entravam por decisão de LLM); cada componente novo
  custava uma chamada de orquestrador e uma entrada no índice de decisões para reproduzir uma
  decisão já escrita em código. Agora o gatilho só dispara para spec sem agente dono
  (referência órfã) e o despacho determinístico volta a ser alcançável.
- `profundidade_cadeia` nunca lia `supersedes`, apesar da docstring e do prompt do
  `orquestrador-llm` exigirem o campo: contava a cardinalidade das entradas relacionadas. Três
  decisões INDEPENDENTES sobre os mesmos arquivos escalavam um projeto saudável para
  intervenção humana. Agora mede o comprimento da maior cadeia real de `supersedes`, com
  proteção contra índice cíclico.
- `orquestrador-llm`: a ação para `spec_ausente` foi reescrita para refletir a nova semântica
  do gatilho (referência órfã, não spec pendente).

Projetos em andamento não precisam de migração: o contrato de saída de `decide.py` (as três
formas de JSON) não mudou, e entradas de decisão já gravadas continuam válidas — as antigas
sem `supersedes` passam a contar como cadeias independentes, que é o comportamento correto.

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
