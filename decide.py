#!/usr/bin/env python3
"""
orchestrator/decide.py

Camada de decisão determinística do Orquestrador. Não invoca nada, não
executa nada — só lê o estado dos arquivos do projeto e devolve, em JSON,
qual é a próxima ação correta. Quem executa a ação (via Task, no Claude
Code) é a sessão principal (seguindo CLAUDE.md) ou o agente orquestrador-llm.

Uso:
    python orchestrator/decide.py <tarefa_id>

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

def gatilho_spec_ausente(tarefa: dict):
    """Alguma spec referenciada pela tarefa não existe no repositório."""
    ausentes = [
        s for s in tarefa.get("specs_referenciadas", [])
        if not (ROOT / s).exists()
    ]
    if ausentes:
        return ausentes
    return None


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
    Conta quantas decisões encadeadas via `supersedes` já existem para este
    par (gatilho, arquivos). Usado para forçar escalated_human sem depender
    de julgamento da LLM.
    """
    entradas = carregar_lista_yaml(DECISIONS_INDEX)
    relacionadas = [
        e for e in entradas
        if e.get("gatilho") == gatilho
        and set(e.get("arquivos_envolvidos", [])) == set(arquivos)
    ]
    return len(relacionadas)


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
            "motivo": "Uso incorreto: python orchestrator/decide.py <tarefa_id>",
        }))
        sys.exit(1)

    resultado = decidir(sys.argv[1])
    print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()
