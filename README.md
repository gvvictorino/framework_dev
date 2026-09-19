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

## Requisitos

**Ambiente padrão: Linux.** Em estações Windows, isso significa **WSL** (Ubuntu ou
equivalente) — não Git Bash, não PowerShell. Os comandos abaixo, os caminhos canônicos
(`~/.claude-agent-framework`, `~/.claude/agents`) e os três scripts assumem um shell Linux.
Rodar fora desse padrão funciona em alguns pontos e falha em outros, de formas que nem sempre
se anunciam — bit de execução que o sistema de arquivos não guarda, separador de caminho
diferente nos registros de decisão. Padronizar a plataforma remove essa classe inteira de
divergência entre máquinas, que é justamente o que esta arquitetura existe para evitar.

Trabalhe com o repositório dentro do sistema de arquivos do Linux (`~/...`), não no do Windows
montado em `/mnt/c` — ali o desempenho cai e as permissões de arquivo não se comportam como o
Linux espera.

- **git** — não é opcional nem detalhe de instalação: todo o estado da arquitetura (specs,
  backlog, decisões) vive em arquivos versionados, e `atualizar.sh` busca novas versões por
  `git pull`.
- **bash** — os três scripts (`setup-machine.sh`, `bootstrap-project.sh`, `atualizar.sh`).
- **Python 3.10 ou superior** — `decide.py` anota assinaturas com `X | None`, sintaxe que o
  interpretador avalia no momento da definição. Em 3.9 o script não chega a rodar.
- **pyyaml** — `decide.py` lê o backlog e o frontmatter das specs em YAML.

```bash
pip install pyyaml
```

Nenhum dos scripts instala o `pyyaml`; a forma de instalar fica a seu critério (`pip`, `pipx`,
gerenciador da distribuição, virtualenv). Sem a biblioteca, `decide.py` não quebra — devolve
`escalar_humano` com o motivo explícito. O efeito prático, porém, é que **toda** decisão de
roteamento para em intervenção humana até você instalá-la, e o sintoma aparece como um agente
pedindo ajuda, não como erro de instalação.

## Uso básico

```bash
pip install pyyaml

git clone <este-repositório> ~/.claude-agent-framework
~/.claude-agent-framework/setup-machine.sh

~/.claude-agent-framework/bootstrap-project.sh /caminho/do/seu/projeto
```

Detalhes de funcionamento — regras de cada agente, formato dos arquivos de estado, os quatro
gatilhos do roteamento determinístico — estão documentados dentro dos próprios arquivos em
`agents/` e em `decide.py`.

Quem vai **trabalhar neste repositório**, e não apenas usá-lo, deve ler antes
[`docs/contexto-claude.md`](./docs/contexto-claude.md): o que configurar em cada estação, por
que o push exige endereço noreply, e as armadilhas de histórico que já custaram uma versão.
