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

## [1.0.5] — 2026-09-19

Correção da P1 da auditoria de 2026-09-19: o agente `revisor-qualidade` era inalcançável pelo
roteamento determinístico. Verificado em projeto sintético antes e depois.

O Implementador marcava `implementado: true` e, no passo seguinte do mesmo prompt, movia a
tarefa para `done.md`. Mas `decide.py` só lê esse campo enquanto a tarefa está em
`in-progress.md`; tudo que está em `done.md` roteia para o Documentador. O estado que aciona o
Revisor existia apenas dentro de uma execução do Implementador, nunca entre duas invocações —
o passo 3 do prompt se justificava dizendo que o campo serve "para rotear a próxima chamada
para o Revisor", e o passo 4 destruía exatamente isso. Em consequência, o Documentador rodava
sem o gap-report `ok` que o próprio prompt dele exige, e `done.md` acumulava tarefa nunca
revisada.

- `implementador`: o passo 4 deixa de mover a tarefa. Ele marca `implementado: true`, grava o
  resumo de uma linha e PARA. A entrada em `in-progress.md` com o campo marcado passa a ser,
  explicitamente, a fila de revisão.
- `revisor-qualidade`: ganhou `Edit` e o fechamento do ciclo. Com gap-report `ok`, move a
  entrada para `done.md`; com `divergente` ou `falha_tecnica`, devolve `implementado: false`,
  incrementa `ciclos_sem_progresso` e preenche `origem_gap`. Sem devolver o campo haveria laço
  — `decide.py` rotearia ao Revisor de novo para re-revisar código que ninguém mudou; sem
  `origem_gap`, o gatilho `gap_sem_tarefa` abriria uma segunda tarefa para a divergência que já
  voltou ao Implementador.
- `decide.py`: só a docstring do módulo, descrevendo a semântica ampliada de `origem_gap` (o
  gap que a tarefa trata, tenha ela nascido dele ou sido devolvida por ele) e o novo ponto de
  parada de `implementado`. Nenhuma linha de comportamento alterada.

Escolha de desenho, entre as duas opções que a auditoria deixou em aberto: os três arquivos de
`/tasks/` são estado de fluxo, não de responsável. Tarefa aguardando revisão continua em
andamento — o trabalho não foi aceito. A granularidade de "com quem está" fica no campo
`implementado`, que já existia e já é espelhado como checkbox pela skill `sincronizar-notion`.
A alternativa (rotear tarefa em `done.md` pela existência do gap-report) manteria `done.md`
significando "não necessariamente pronto" e exigiria mover tarefa reprovada de volta de `done`.

Migração para projetos em andamento: tarefa que já esteja em `done.md` sem gap-report
correspondente foi fechada sem revisão sob o comportamento antigo. Se quiser revisá-la, mova a
entrada de volta para `in-progress.md` mantendo `implementado: true`. O contrato de saída de
`decide.py` não mudou.

Esta correção não é coberta pela suíte: o defeito estava no contrato entre prompt e roteador,
não dentro de `decide.py`. Os dois casos relevantes ("in-progress implementado →
revisor-qualidade" e "done → documentador") sempre passaram isolados, e é precisamente por
isso que o bug sobreviveu — nada encadeava o que o Implementador fazia entre eles.

## [1.0.4] — 2026-09-19

Declaração das dependências de execução no `README.md`, que não as registrava em lugar nenhum,
e um documento de contexto para quem abre o repositório noutra estação.

- Seção **Requisitos** acrescentada: `git`, `bash`, Python 3.10+ e `pyyaml`. A omissão do
  `pyyaml` era a mais cara das quatro. `decide.py` trata a ausência com elegância — devolve
  `escalar_humano` com o motivo correto — e é justamente por isso que o sintoma engana: numa
  máquina recém-instalada, *toda* tarefa cai em intervenção humana, o que se parece com um
  projeto mal configurado, não com uma biblioteca faltando.
- O piso de Python 3.10 não é arbitrário, mas também não estava escrito: `decide.py` anota
  assinaturas com `X | None` sem `from __future__ import annotations`, então o interpretador
  avalia a anotação na definição e a 3.9 falha ao carregar o módulo.
- `pip install pyyaml` acrescentado também ao bloco de **Uso básico**, que é o trecho que as
  pessoas copiam na prática.
- **`docs/contexto-claude.md`** criado: o que uma estação nova precisa saber *antes* de mexer
  aqui e que não cabe em changelog nem em README — configuração por máquina (incluindo
  `core.filemode false` no Windows), o endereço noreply obrigatório para `git push`, o
  incidente de histórico que gerou a v1.0.2 e as decisões de arquitetura que os arquivos não
  revelam isoladamente. Referenciado no fim do README.

Sem impacto em projetos em andamento: a mudança é só de documentação, nenhum arquivo de
comportamento foi tocado. `setup-machine.sh` segue sem instalar o `pyyaml` de propósito — como
instalar (`pip`, `pipx`, distribuição, virtualenv) continua sendo decisão de quem instala.

## [1.0.3] — 2026-09-18

Três correções derivadas da auditoria do projeto `analistajuridico`, todas verificadas contra o
estado real antes de virar mudança.

- `bootstrap-project.sh` passou a **validar** o caminho canônico em vez de presumi-lo. Em modo
  `--shared` ele escreve `$HOME/.claude-agent-framework/decide.py` no `CLAUDE.md` gerado, e antes
  fazia isso sem checar se o framework estava instalado ali. Quando não estava, o projeto nascia
  com um Passo 1 que falha — e como a instrução do próprio `CLAUDE.md` nesse caso é PARAR, o
  projeto ficava travado sem nenhum sinal na hora do bootstrap. O caminho continua fixo de
  propósito: a arquitetura depende de uma cópia única do framework em local canônico, com os
  artefatos resolvidos relativos ao projeto chamador (`ROOT = Path.cwd()`); derivá-lo de
  `SCRIPT_DIR` devolveria variabilidade a um caminho que precisa ser igual em toda a máquina.
  Fixo, porém não presumido — agora avisa e diz como corrigir.
- `documentador` ganhou `Edit` nas tools e a regra explícita de ler `docs/architecture.md` inteiro
  antes de escrever. O arquivo é acumulativo e o agente só tinha `Write`: a mesma classe de risco
  que motivou acrescentar `Edit` ao `planner` e ao `llm-qualification` na 1.0.0. A perda não
  aparece na primeira execução, com o arquivo vazio — aparece na segunda.
- Referências a `orchestrator/decide.py` removidas da prosa dos agentes e das skills, e também da
  **mensagem de uso do próprio `decide.py`**, que imprimia esse caminho na saída de erro. O rótulo
  descrevia o modo `--local` enquanto a instalação padrão é `--shared`.

Sem impacto em projetos em andamento: o contrato de saída de `decide.py` não mudou, e a única
alteração de comportamento é um aviso novo no bootstrap.

## [1.0.2] — 2026-09-18

Restauração da v1.0.1 e correção do bit de execução dos scripts. O commit `78b97c7`
("Add files via upload") substituiu o histórico do repositório e reverteu a `main` para o
conteúdo da 1.0.0: `decide.py` voltou ao estado com os dois bugs de roteamento, e
`tests/test_decide.py`, o relatório de auditoria e a entrada `[1.0.1]` deste changelog
sumiram. A tag `v1.0.1` continuou existindo no remoto, mas apontando para uma linhagem órfã,
inalcançável a partir de qualquer branch — quem clonasse o repositório recebia 1.0.0.
Regressão medida rodando a suíte contra os dois `decide.py`: 16/16 na v1.0.1, 11/16 na `main`.

- Conteúdo da 1.0.1 reintroduzido numa linhagem alcançável a partir da `main`, com a suíte de
  regressão de volta em `tests/test_decide.py`.
- Bit de execução restaurado em `setup-machine.sh`, `bootstrap-project.sh` e `atualizar.sh`
  (`100644` → `100755`). O upload zerou a permissão nos três, o que quebrava as duas formas
  documentadas de uso: o README instrui a rodar `~/.claude-agent-framework/setup-machine.sh`
  diretamente, e `atualizar.sh` invoca `"$SCRIPT_DIR/setup-machine.sh" --force` na etapa de
  propagação — ambos falhavam com `Permission denied`.

Quem instalou a partir da `main` depois do upload está com 1.0.0 e precisa atualizar: os dois
bugs de roteamento de `decide.py` descritos na 1.0.1 estavam ativos nessa cópia.

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
