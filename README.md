# Arquitetura de agentes para desenvolvimento com Claude Code

> **Repositório público, mas não open source.** Veja [LICENSE](./LICENSE) — visibilidade para
> portfólio, sem permissão de uso por terceiros.

Framework de agentes especializados para desenvolvimento de software com [Claude
Code](https://claude.com/claude-code), desenhado para reduzir dependência de contexto longo de
conversa: todo estado relevante (specs, decisões, backlog) vive em arquivos versionados em git,
não em memória de sessão. Qualquer agente, em qualquer máquina, reconstrói o que precisa saber
lendo o repositório — nunca o histórico de chat.

## O que tem aqui

- **8 agentes especialistas** (`agents/`) — Planner, Design, Data Pipeline, LLM Qualification,
  Implementador, Revisor de Qualidade, Documentador, e um Orquestrador-LLM para resolver
  conflitos com escopo fechado.
- **`decide.py`** — camada de roteamento determinística. Decide qual agente roda a seguir por
  regras verificáveis (existência de spec, versão, profundidade de reabertura de conflito), não
  por julgamento de LLM a cada passo. Só escala para julgamento de LLM em casos fechados e
  específicos.
- **2 skills** (`skills/`) — auditoria da própria arquitetura (`/auditoria-arquitetura`) e
  espelho opcional do backlog no Notion, via de mão única (`/sincronizar-notion`).
- **Scripts de instalação e atualização** — `setup-machine.sh` (instala numa máquina),
  `bootstrap-project.sh` (cria o esqueleto num projeto), `atualizar.sh` (busca novas versões
  via git e propaga).

## Por que existe

A motivação original: um agente de IA que depende só de contexto de conversa perde
continuidade entre sessões, entre máquinas, e conforme o histórico cresce. Este framework move
toda decisão de estado para fora da conversa — arquivos, git, e uma camada de roteamento que é
código comum, não prompt. O objetivo é um fluxo de desenvolvimento que continua de onde parou,
em qualquer computador, sem precisar "reexplicar" nada a um agente novo.

## Estrutura

```
agents/           8 subagentes do Claude Code (.claude/agents/*.md)
skills/           2 skills (.claude/skills/*/SKILL.md)
decide.py         roteamento determinístico
setup-machine.sh  instala agentes/skills em ~/.claude/ nesta máquina
bootstrap-project.sh   cria CLAUDE.md + docs/ + tasks/ num projeto
atualizar.sh      git pull + propagação, com changelog
templates/        template de CLAUDE.md
VERSION           versão semântica atual
CHANGELOG.md      histórico de mudanças
```

## Uso básico

```bash
git clone <este-repositório> ~/.claude-agent-framework
~/.claude-agent-framework/setup-machine.sh

~/.claude-agent-framework/bootstrap-project.sh /caminho/do/seu/projeto
```

Detalhes de funcionamento — regras de cada agente, formato dos arquivos de estado, os quatro
gatilhos do roteamento determinístico — estão documentados dentro dos próprios arquivos em
`agents/` e em `decide.py`.
