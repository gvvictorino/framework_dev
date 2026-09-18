#!/usr/bin/env python3
"""
decide.py

Camada de decisão determinística do Orquestrador. Não invoca nada, não
executa nada — só lê o estado dos arquivos do projeto e devolve, em JSON,
qual é a próxima ação correta. Quem executa a ação (via Task, no Claude
Code) é a sessão principal (seguindo CLAUDE.md) ou o agente orquestrador-llm.

Uso:
    python3 <caminho-do-framework>/decide.py <tarefa_id>

O caminho concreto é fixado pelo bootstrap no CLAUDE.md de cada projeto; na
instalação padrão é $HOME/.claude-agent-framework/decide.py. O script opera
sempre sobre o diretório de onde foi chamado, não sobre onde ele mesmo está.

Saída (stdout, JSON), sempre um destes três formatos:
    {"acao": "invocar_agente", "agente": "<nome>"}
    {"acao": "invocar_agente", "agente": "orquestrador-llm", "gatilho": "<nome>",
     "arquivos_envolvidos": [...]}
    {"acao": "escalar_humano", "motivo": "<texto>"}

ASSUNÇÕES DE FORMATO — documentadas aqui porque não existiam antes deste
arquivo. Se as specs de agente (.claude/agents/*.md) forem ajustadas para
gerar tarefas nesse formato, o script funciona sem alteração:

  backlog.md / in-progress.md / done.md: cada um é uma lista YAML pura
  (sem prosa em volta), campos por tarefa:
    id, componente, tipo, specs_referenciadas, status, gerado_por
    requer_qualificacao: bool          # NOVO — só existe se tipo pedir LLM
    origem_gap: str | None             # NOVO — preenchido se a tarefa nasceu
                                        # de um gap-report divergente, aponta
                                        # para o nome do arquivo de gap-report
    implementado: bool                 # NOVO — o Implementador marca true
                                        # ao terminar, antes do Revisor rodar

  tech-stack.md: frontmatter YAML (delimitado por ---) com chave `componentes`

  decisions/orchestrator/index.md: lista YAML de entradas:
    id, gatilho, arquivos_envolvidos, status, supersedes (opcional)
    `supersedes` aponta para o `id` da decisão que esta entrada reabre. É o
    que define o comprimento da cadeia; entradas sem ele são independentes.

  gap-reports/<tarefa_id>.md: cabeçalho com linhas `componente:` e `status:`
  (não é frontmatter YAML — é lido por regex simples, conforme o formato já
  definido no prompt do agente revisor-qualidade)
"""

import sys
import json
import re
from pathlib import Path

try:
    import yaml
except ImportError:
    print(json.dumps({
        "acao": "escalar_humano",
        "motivo": "Dependência 'pyyaml' não instalada. Rode: pip install pyyaml"
    }))
    sys.exit(1)

ROOT = Path.cwd()
# ROOT é o diretório de trabalho atual, não a localização deste arquivo — isso permite manter
# uma única cópia de decide.py fora de cada projeto (ex: ~/.claude-agent-framework/decide.py) e
# invocá-la de dentro de qualquer projeto via caminho absoluto. O script sempre opera sobre o
# projeto em que foi chamado, nunca sobre a pasta onde ele mesmo está guardado.
BACKLOG = ROOT / "tasks" / "backlog.md"
IN_PROGRESS = ROOT / "tasks" / "in-progress.md"
DONE = ROOT / "tasks" / "done.md"
TECH_STACK = ROOT / "docs" / "tech-stack.md"
DECISIONS_INDEX = ROOT / "docs" / "decisions" / "orchestrator" / "index.md"
GAP_REPORTS_DIR = ROOT / "docs" / "decisions" / "gap-reports"
SPECS_DIR = ROOT / "docs" / "specs"

PROFUNDIDADE_MAXIMA = 3

# Qual agente produz cada categoria de spec, por diretório sob docs/specs/.
# É o que permite a gatilho_spec_ausente distinguir "spec que ainda não foi
# gerada" (roteamento determinístico) de "referência órfã" (divergência real).
DONOS_DE_SPEC = {
    "functional": "planner",
    "design": "design",
    "data-pipeline": "data-pipeline",
    "qualification": "llm-qualification",
}

# Ordem de dependência entre specs: a funcional precede as de componente, e o
# schema de data-pipeline precede a spec de qualification que o referencia.
PRIORIDADE_ESPECIALISTAS = ("planner", "design", "data-pipeline", "llm-qualification")


# ---------------------------------------------------------------------------
# Leitura de estado — funções puras, sem efeito colateral
# ---------------------------------------------------------------------------

def carregar_lista_yaml(path: Path) -> list:
    """Carrega um arquivo de lista YAML pura. Retorna [] se não existir."""
    if not path.exists():
        return []
    conteudo = path.read_text(encoding="utf-8")
    dados = yaml.safe_load(conteudo)
    return dados or []


def carregar_frontmatter(path: Path) -> dict:
    """Carrega o bloco YAML entre --- --- no topo de um arquivo markdown."""
    if not path.exists():
        return {}
    conteudo = path.read_text(encoding="utf-8")
    m = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n", conteudo, re.DOTALL)
    if not m:
        return {}
    return yaml.safe_load(m.group(1)) or {}


def localizar_tarefa(tarefa_id: str):
    """Procura a tarefa nos três arquivos de estado. Retorna (tarefa, arquivo)."""
    for path in (BACKLOG, IN_PROGRESS, DONE):
        for tarefa in carregar_lista_yaml(path):
            if tarefa.get("id") == tarefa_id:
                return tarefa, path
    return None, None


def extrair_versao_spec(path: Path) -> int | None:
    """Lê o campo `versao:` do topo de um arquivo de spec (frontmatter ou não)."""
    if not path.exists():
        return None
    conteudo = path.read_text(encoding="utf-8")
    m = re.search(r"^versao:\s*(\d+)", conteudo, re.MULTILINE)
    return int(m.group(1)) if m else None


def extrair_campo_gap_report(path: Path, campo: str) -> str | None:
    """Lê um campo simples (ex: `status:`, `componente:`) de um gap-report."""
    if not path.exists():
        return None
    conteudo = path.read_text(encoding="utf-8")
    m = re.search(rf"^{campo}:\s*(.+)$", conteudo, re.MULTILINE)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Gatilhos — cada um é uma função pura que retorna arquivos envolvidos ou None
# ---------------------------------------------------------------------------

def agente_dono_da_spec(spec_rel: str, tarefa: dict) -> str | None:
    """
    Qual agente especialista PRODUZ esta spec, se ela estiver faltando.
    Retorna None quando nenhum agente do framework a produz — só nesse caso a
    ausência é uma divergência real, que precisa do orquestrador-llm.

    Specs por componente (design/data-pipeline/qualification) só têm dono se o
    nome do arquivo corresponder ao componente da própria tarefa: uma tarefa
    que referencia a spec de design de OUTRO componente é referência órfã, não
    trabalho pendente do agente design nesta tarefa.
    """
    partes = Path(spec_rel).parts
    if len(partes) < 3 or partes[0] != "docs" or partes[1] != "specs":
        return None

    categoria = partes[2]
    dono = DONOS_DE_SPEC.get(categoria)
    if dono is None:
        return None

    if categoria != "functional":
        if Path(spec_rel).name != f"{tarefa.get('componente')}.md":
            return None

    return dono


def especialista_para_spec_faltante(tarefa: dict) -> str | None:
    """
    Qual especialista precisa rodar para produzir as specs ausentes que esta
    tarefa referencia. Determinístico: usa PRIORIDADE_ESPECIALISTAS (ordem de
    dependência), nunca a ordem em que as specs aparecem na tarefa.
    """
    donos = {
        agente_dono_da_spec(s, tarefa)
        for s in tarefa.get("specs_referenciadas", [])
        if not (ROOT / s).exists()
    }
    donos.discard(None)

    for agente in PRIORIDADE_ESPECIALISTAS:
        if agente in donos:
            return agente
    return None


def gatilho_spec_ausente(tarefa: dict):
    """
    Dispara APENAS para specs ausentes que nenhum agente especialista produz.

    Antes esta função devolvia TODA spec referenciada e inexistente. Como os
    gatilhos são avaliados antes de mapear_tarefa_para_agente(), ela
    interceptava o estado normal de uma tarefa recém-criada — o planner lista
    docs/specs/design/<componente>.md em specs_referenciadas justamente porque
    a spec ainda não existe — e mandava para o orquestrador-llm. Efeitos:

      1. Todo o despacho para especialista em mapear_tarefa_para_agente() era
         código inalcançável: os agentes planner, design, data-pipeline e
         llm-qualification só entravam por decisão de LLM.
      2. Cada componente novo custava uma chamada de LLM e uma entrada no
         índice de decisões para reproduzir uma decisão já escrita em código.
      3. Essas entradas alimentavam o circuit breaker de profundidade, que
         escalava para humano um projeto sem nenhuma divergência real.

    Spec ausente COM dono não é divergência — é o estado esperado antes do
    especialista rodar, e o roteamento determinístico já sabe quem chamar.
    """
    orfas = [
        s for s in tarefa.get("specs_referenciadas", [])
        if not (ROOT / s).exists() and agente_dono_da_spec(s, tarefa) is None
    ]
    return orfas or None


def gatilho_spec_conflict(tarefa: dict):
    """
    Checagem específica: se a tarefa depende de qualification-spec, a versão
    do schema que ela referencia (schema_referencia) precisa bater com a
    versao atual do data-pipeline-spec do mesmo componente.
    """
    componente = tarefa.get("componente")
    qual_spec = SPECS_DIR / "qualification" / f"{componente}.md"
    pipeline_spec = SPECS_DIR / "data-pipeline" / f"{componente}.md"

    if not qual_spec.exists() or not pipeline_spec.exists():
        return None

    conteudo_qual = qual_spec.read_text(encoding="utf-8")
    m = re.search(r"schema_referencia:.*#v(\d+)", conteudo_qual)
    if not m:
        return None
    versao_referenciada = int(m.group(1))
    versao_atual = extrair_versao_spec(pipeline_spec)

    if versao_atual is not None and versao_referenciada != versao_atual:
        return [str(qual_spec.relative_to(ROOT)), str(pipeline_spec.relative_to(ROOT))]
    return None


def gatilho_gap_sem_tarefa(tarefa: dict):
    """
    Existe algum gap-report `divergente` para este componente sem nenhuma
    tarefa (em backlog ou in-progress) que o referencie via `origem_gap`.
    """
    componente = tarefa.get("componente")
    if not GAP_REPORTS_DIR.exists():
        return None

    todas_tarefas = (
        carregar_lista_yaml(BACKLOG) + carregar_lista_yaml(IN_PROGRESS)
    )
    origens_ja_tratadas = {
        t.get("origem_gap") for t in todas_tarefas if t.get("origem_gap")
    }

    orfaos = []
    for gap_path in GAP_REPORTS_DIR.glob("*.md"):
        if extrair_campo_gap_report(gap_path, "componente") != componente:
            continue
        if extrair_campo_gap_report(gap_path, "status") != "divergente":
            continue
        if gap_path.name not in origens_ja_tratadas:
            orfaos.append(str(gap_path.relative_to(ROOT)))

    return orfaos or None


def gatilho_tarefa_travada(tarefa: dict, arquivo_atual: Path):
    """
    LEITURA PURA. Não incrementa nem grava nada — só lê o campo `ciclos_sem_progresso`
    que o próprio Implementador mantém (ver implementador.md) e verifica se atingiu o
    limite. Antes esta função escrevia em in-progress.md a cada chamada, o que violava
    o contrato "sem efeito colateral" da docstring do módulo e inflava o contador com
    chamadas de diagnóstico, não com tentativas reais sem progresso — corrigido.
    """
    LIMITE_CICLOS = 5
    if arquivo_atual != IN_PROGRESS:
        return None

    if tarefa.get("ciclos_sem_progresso", 0) >= LIMITE_CICLOS:
        return [f"tasks/in-progress.md#{tarefa.get('id')}"]
    return None


GATILHOS = {
    "spec_ausente": gatilho_spec_ausente,
    "spec_conflict": gatilho_spec_conflict,
    "gap_sem_tarefa": gatilho_gap_sem_tarefa,
}


# ---------------------------------------------------------------------------
# Profundidade de cadeia (supersedes) — circuit breaker antes de chamar LLM
# ---------------------------------------------------------------------------

def profundidade_cadeia(gatilho: str, arquivos: list) -> int:
    """
    Comprimento da MAIOR cadeia de reaberturas encadeadas via `supersedes`
    para este par (gatilho, arquivos). Usado para forçar escalated_human sem
    depender de julgamento da LLM.

    Antes esta função devolvia len(relacionadas) e nunca lia `supersedes`,
    contrariando a própria docstring e o prompt do orquestrador-llm, que exige
    gravar o campo. Efeito prático: três decisões INDEPENDENTES sobre os mesmos
    arquivos — sem nenhuma reabertura — escalavam o projeto para intervenção
    humana. Decisões sem `supersedes` são cadeias de comprimento 1 e não se
    somam entre si.
    """
    entradas = carregar_lista_yaml(DECISIONS_INDEX)
    relacionadas = {
        e.get("id"): e
        for e in entradas
        if e.get("gatilho") == gatilho
        and set(e.get("arquivos_envolvidos", [])) == set(arquivos)
        and e.get("id") is not None
    }
    if not relacionadas:
        return 0

    def comprimento(entrada_id, visitados: frozenset) -> int:
        # `supersedes` aponta para a decisão que esta entrada substitui, então
        # a cadeia é percorrida para trás. `visitados` impede laço infinito num
        # índice corrompido (A supersedes B, B supersedes A).
        if entrada_id in visitados:
            return 0
        anterior = relacionadas[entrada_id].get("supersedes")
        if anterior is None or anterior not in relacionadas:
            return 1
        return 1 + comprimento(anterior, visitados | {entrada_id})

    return max(comprimento(i, frozenset()) for i in relacionadas)


# ---------------------------------------------------------------------------
# Mapeamento tarefa → agente especialista (quando nenhum gatilho dispara)
# ---------------------------------------------------------------------------

def caminho_spec_functional(tarefa: dict) -> bool:
    return any(
        s.startswith("docs/specs/functional/") and (ROOT / s).exists()
        for s in tarefa.get("specs_referenciadas", [])
    )


def caminho_spec_design_ok(tarefa: dict) -> bool:
    return (SPECS_DIR / "design" / f"{tarefa.get('componente')}.md").exists()


def caminho_spec_pipeline_ok(tarefa: dict) -> bool:
    return (SPECS_DIR / "data-pipeline" / f"{tarefa.get('componente')}.md").exists()


def caminho_spec_qualification_ok(tarefa: dict) -> bool:
    return (SPECS_DIR / "qualification" / f"{tarefa.get('componente')}.md").exists()


def mapear_tarefa_para_agente(tarefa: dict, arquivo_atual: Path) -> str:
    tipo = tarefa.get("tipo")

    if arquivo_atual == DONE:
        # Ciclo de implementação fechado; falta só documentar, se ainda
        # não foi feito. decide.py não checa se architecture.md já reflete
        # esta tarefa — isso fica a cargo do próprio Documentador, que é
        # idempotente por design (lê o que já existe antes de escrever).
        return "documentador"

    if arquivo_atual == IN_PROGRESS:
        if tarefa.get("implementado"):
            return "revisor-qualidade"
        return "implementador"

    # arquivo_atual == BACKLOG
    # 1. Despacho guiado pelas specs que a tarefa REFERENCIA e que ainda não
    #    existem. Este caminho era inalcançável: gatilho_spec_ausente
    #    interceptava todos esses casos e os mandava ao orquestrador-llm.
    especialista = especialista_para_spec_faltante(tarefa)
    if especialista:
        return especialista

    # 2. Rede de segurança por TIPO da tarefa: cobre spec obrigatória que o
    #    planner esqueceu de listar em specs_referenciadas.
    if not caminho_spec_functional(tarefa):
        return "planner"
    if tipo == "ui" and not caminho_spec_design_ok(tarefa):
        return "design"
    if tipo in ("data_pipeline", "worker") and not caminho_spec_pipeline_ok(tarefa):
        return "data-pipeline"
    if tarefa.get("requer_qualificacao") and not caminho_spec_qualification_ok(tarefa):
        return "llm-qualification"

    return "implementador"


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def decidir(tarefa_id: str) -> dict:
    tarefa, arquivo_atual = localizar_tarefa(tarefa_id)
    if tarefa is None:
        return {
            "acao": "escalar_humano",
            "motivo": f"Tarefa '{tarefa_id}' não encontrada em backlog, "
                      f"in-progress ou done.",
        }

    for nome_gatilho, funcao in GATILHOS.items():
        resultado = funcao(tarefa)
        if resultado:
            profundidade = profundidade_cadeia(nome_gatilho, resultado)
            if profundidade >= PROFUNDIDADE_MAXIMA:
                return {
                    "acao": "escalar_humano",
                    "motivo": (
                        f"Gatilho '{nome_gatilho}' reaberto {profundidade} vezes "
                        f"para os mesmos arquivos — indica problema de processo, "
                        f"não caso pontual. Ver docs/decisions/orchestrator/."
                    ),
                }
            return {
                "acao": "invocar_agente",
                "agente": "orquestrador-llm",
                "gatilho": nome_gatilho,
                "arquivos_envolvidos": resultado,
            }

    # gatilho_tarefa_travada é leitura pura (ver docstring da função) — checado à parte
    # dos outros três só porque precisa do arquivo_atual, não porque muta algo
    resultado_travada = gatilho_tarefa_travada(tarefa, arquivo_atual)
    if resultado_travada:
        profundidade = profundidade_cadeia("tarefa_travada_N_ciclos", resultado_travada)
        if profundidade >= PROFUNDIDADE_MAXIMA:
            return {
                "acao": "escalar_humano",
                "motivo": f"Tarefa '{tarefa_id}' travada repetidamente — "
                          f"requer intervenção humana.",
            }
        return {
            "acao": "invocar_agente",
            "agente": "orquestrador-llm",
            "gatilho": "tarefa_travada_N_ciclos",
            "arquivos_envolvidos": resultado_travada,
        }

    agente = mapear_tarefa_para_agente(tarefa, arquivo_atual)
    return {"acao": "invocar_agente", "agente": agente}


def main():
    if len(sys.argv) != 2:
        print(json.dumps({
            "acao": "escalar_humano",
            "motivo": "Uso incorreto: o script de decisão espera exatamente um argumento, o <tarefa_id>.",
        }))
        sys.exit(1)

    resultado = decidir(sys.argv[1])
    print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()
