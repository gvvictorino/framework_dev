#!/usr/bin/env python3
"""
decide.py

Camada de decisão determinística do Orquestrador. Não invoca nada, não
executa nada — só lê o estado dos arquivos do projeto e devolve, em JSON,
qual é a próxima ação correta. Quem executa a ação (via Task, no Claude
Code) é a sessão principal (seguindo CLAUDE.md) ou o agente orquestrador-llm.

Uso:
    python3 <caminho-do-framework>/decide.py <tarefa_id>   # decide sobre uma tarefa
    python3 <caminho-do-framework>/decide.py               # escolhe a próxima e decide

Sem argumento, o script aplica a regra de seleção de `proxima_tarefa()` e acrescenta
`tarefa_id` ao JSON, para que quem chamou saiba sobre qual tarefa ele decidiu. Com id
explícito a saída é a mesma de sempre, sem campo novo.

O caminho concreto é fixado pelo bootstrap no CLAUDE.md de cada projeto; na
instalação padrão é $HOME/.claude-agent-framework/decide.py. O script opera
sempre sobre o diretório de onde foi chamado, não sobre onde ele mesmo está.

Saída (stdout, JSON), sempre um destes quatro formatos:
    {"acao": "invocar_agente", "agente": "<nome>"}
    {"acao": "invocar_agente", "agente": "orquestrador-llm", "gatilho": "<nome>",
     "arquivos_envolvidos": [...]}
    {"acao": "escalar_humano", "motivo": "<texto>"}
    {"acao": "nada_a_fazer", "motivo": "<texto>"}

O contrato vale também no erro: arquivo de estado com YAML inválido ou forma
inesperada vira `escalar_humano` com o arquivo e o detalhe no motivo, nunca
traceback com stdout vazio. Nesse caso, e no de pyyaml ausente, o exit code é 1
— o JSON continua no stdout, e é ele que a sessão principal deve reportar.

ASSUNÇÕES DE FORMATO — documentadas aqui porque não existiam antes deste
arquivo. Se as specs de agente (.claude/agents/*.md) forem ajustadas para
gerar tarefas nesse formato, o script funciona sem alteração:

  backlog.md / in-progress.md / done.md: cada um é uma lista YAML pura
  (sem prosa em volta), campos por tarefa:
    id, componente, tipo, specs_referenciadas, status, gerado_por
    requer_qualificacao: bool          # NOVO — só existe se tipo pedir LLM
    origem_gap: str | None             # nome do arquivo de gap-report que esta
                                        # tarefa está tratando — seja porque
                                        # nasceu dele (tarefa corretiva criada
                                        # pelo orquestrador) ou porque o Revisor
                                        # a devolveu ao Implementador por causa
                                        # dele. É o que marca o gap como já
                                        # reivindicado para gatilho_gap_sem_tarefa
    documentado: bool                  # o Documentador marca true depois de refletir
                                        # a tarefa em architecture.md. É o que encerra
                                        # o ciclo: sem ele, a seleção automática de
                                        # tarefa escolheria para sempre a primeira
                                        # entrada de done.md, que sempre roteia para
                                        # o Documentador. Ausente conta como false
    implementado: bool                 # o Implementador marca true e PARA; a
                                        # tarefa fica em in-progress.md como fila
                                        # de revisão. Quem move para done.md é o
                                        # Revisor, e só com gap-report `ok`

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

class EstadoMalformado(Exception):
    """
    Arquivo de estado do projeto ilegível: YAML inválido ou forma inesperada.

    Levantada pelos leitores e capturada no ponto de entrada, que a converte na
    saída `escalar_humano` que a docstring do módulo promete. Sem isso, um
    arquivo escrito torto — cenário plausível, já que quem os escreve são
    agentes de LLM — produzia traceback e stdout VAZIO, e a sessão principal
    parava sem motivo utilizável para reportar.
    """


def _rotulo(path: Path) -> str:
    """Caminho legível para mensagem de erro, relativo ao projeto quando possível."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _detalhe(erro: Exception) -> str:
    """Achata a mensagem multilinha do pyyaml numa linha só, para caber no JSON."""
    return " ".join(str(erro).split())


def carregar_lista_yaml(path: Path) -> list:
    """
    Carrega um arquivo de lista YAML pura. Retorna [] se não existir.

    Valida a forma aqui, e não em cada chamador: os três call sites (busca de
    tarefa, varredura de `origem_gap` e índice de decisões) tratam cada item
    como dict e chamariam `.get` nele.
    """
    if not path.exists():
        return []
    conteudo = path.read_text(encoding="utf-8")
    try:
        dados = yaml.safe_load(conteudo)
    except yaml.YAMLError as e:
        raise EstadoMalformado(f"{_rotulo(path)} não é YAML válido: {_detalhe(e)}")
    if dados is None:
        return []
    if not isinstance(dados, list):
        raise EstadoMalformado(
            f"{_rotulo(path)} deveria ser uma lista YAML pura, sem prosa em volta — "
            f"veio {type(dados).__name__}"
        )
    for i, item in enumerate(dados):
        if not isinstance(item, dict):
            raise EstadoMalformado(
                f"{_rotulo(path)}: a entrada de índice {i} deveria ser um mapeamento "
                f"de campos — veio {type(item).__name__}"
            )
    return dados


def carregar_frontmatter(path: Path) -> dict:
    """Carrega o bloco YAML entre --- --- no topo de um arquivo markdown."""
    if not path.exists():
        return {}
    conteudo = path.read_text(encoding="utf-8")
    m = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n", conteudo, re.DOTALL)
    if not m:
        return {}
    try:
        dados = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        raise EstadoMalformado(
            f"o frontmatter de {_rotulo(path)} não é YAML válido: {_detalhe(e)}"
        )
    if dados is None:
        return {}
    if not isinstance(dados, dict):
        raise EstadoMalformado(
            f"o frontmatter de {_rotulo(path)} deveria ser um mapeamento — "
            f"veio {type(dados).__name__}"
        )
    return dados


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
        # .as_posix() e obrigatorio, nao cosmetico: profundidade_cadeia compara
        # arquivos_envolvidos por igualdade literal de string. str() usa o separador
        # do SO, entao uma decisao gravada no Linux nunca casaria com a mesma
        # divergencia avaliada no Windows, e o circuit breaker falharia ABERTO.
        return [qual_spec.relative_to(ROOT).as_posix(),
                pipeline_spec.relative_to(ROOT).as_posix()]
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
            orfaos.append(gap_path.relative_to(ROOT).as_posix())  # POSIX: ver gatilho_spec_conflict

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

def normalizar_caminhos(caminhos) -> set:
    """
    Conjunto de caminhos comparavel entre sistemas operacionais.

    Entradas ja gravadas no indice antes da v1.1.0 podem ter barra invertida,
    porque os gatilhos usavam o separador do SO. Normalizar na leitura faz o
    historico continuar casando em vez de reiniciar toda cadeia de supersedes
    que tenha sido gravada no Windows.
    """
    return {str(c).replace("\\", "/") for c in caminhos}


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
    for e in entradas:
        envolvidos = e.get("arquivos_envolvidos", [])
        if not isinstance(envolvidos, list):
            # Não dá para ignorar a entrada torta e seguir: o breaker falharia
            # ABERTO, que é exatamente o modo de falha que ele existe para evitar.
            raise EstadoMalformado(
                f"{_rotulo(DECISIONS_INDEX)}: a entrada id={e.get('id')!r} tem "
                f"`arquivos_envolvidos` do tipo {type(envolvidos).__name__}, "
                f"esperado lista"
            )
    relacionadas = {
        e.get("id"): e
        for e in entradas
        if e.get("gatilho") == gatilho
        and normalizar_caminhos(e.get("arquivos_envolvidos", [])) == normalizar_caminhos(arquivos)
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
        # Ciclo de implementação fechado; falta documentar. O caso já documentado
        # não chega aqui — `decidir` o intercepta antes, pelo campo `documentado`.
        # decide.py continua não inspecionando o conteúdo de architecture.md: quem
        # garante que documentar duas vezes não duplica é o próprio Documentador,
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
# Seleção de tarefa — qual é "a próxima", por regra e não por julgamento
# ---------------------------------------------------------------------------

# Terminar o que já começou antes de começar coisa nova. `done.md` vem antes de
# `backlog.md` porque documentar é fechamento de trabalho já feito, não trabalho novo.
ORDEM_DE_SELECAO = (IN_PROGRESS, DONE, BACKLOG)


def _chave_ordenacao(tarefa: dict):
    """
    Ordena por `id` comparando os dígitos como número, não como texto — sem isso
    T-10 viria antes de T-2. Id sem dígito vai para o fim, em ordem alfabética.
    """
    tid = str(tarefa.get("id", ""))
    m = re.search(r"(\d+)", tid)
    return (0, int(m.group(1)), tid) if m else (1, 0, tid)


def tarefa_pendente(tarefa: dict, arquivo: Path) -> bool:
    """
    Tarefa em `done.md` só continua pendente enquanto não tiver `documentado: true`.

    Sem esse campo a seleção automática não termina: `mapear_tarefa_para_agente`
    devolve `documentador` para tudo que está em done.md, então a primeira tarefa
    concluída do projeto seria escolhida como "a próxima" para sempre. A ausência
    do campo conta como não documentada, então projeto anterior à v1.1.0 continua
    se comportando como antes.
    """
    if arquivo == DONE:
        return not tarefa.get("documentado")
    return True


def proxima_tarefa() -> str | None:
    """
    Qual tarefa processar quando o usuário diz só "roda o próximo", sem nomear id.

    A regra é explícita e mora aqui, não no julgamento da sessão principal. Antes
    da v1.1.0 não existia regra nenhuma: o template mandava rodar "o próximo" e o
    script exigia um `<tarefa_id>`, então a escolha caía na sessão — num sistema
    cujo princípio declarado é que decisão de roteamento não é julgamento de LLM.
    A lacuna não aparecia com backlog de uma tarefa só.
    """
    for arquivo in ORDEM_DE_SELECAO:
        candidatas = [
            t for t in carregar_lista_yaml(arquivo) if tarefa_pendente(t, arquivo)
        ]
        if candidatas:
            return min(candidatas, key=_chave_ordenacao).get("id")
    return None


def avisar_se_copia_local_desatualizada() -> None:
    """
    No modo --local do bootstrap, decide.py é copiado para dentro do projeto e
    `atualizar.sh` nunca alcança essa cópia: ele atualiza os agentes em
    ~/.claude/agents para a máquina inteira, mas não o roteador do projeto. Como
    agentes e roteador são acoplados (a v1.0.1 mudou `decide.py` E
    `orquestrador-llm.md` na mesma correção), o projeto passa a rodar agentes
    novos contra roteamento antigo, sem nenhum sinal.

    O aviso sai em STDERR de propósito: stdout é contrato, e quem consome o JSON
    não pode receber texto solto no meio dele.
    """
    propria = Path(__file__).resolve().parent / "VERSION"
    canonica = (Path.home() / ".claude-agent-framework" / "VERSION").resolve()
    if not propria.exists() or not canonica.exists():
        return
    if propria == canonica:
        return  # instalação compartilhada: é literalmente o mesmo arquivo
    try:
        v_propria = propria.read_text(encoding="utf-8").strip()
        v_canonica = canonica.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if v_propria != v_canonica:
        print(
            f"AVISO: esta cópia local de decide.py é da versão {v_propria}, e o "
            f"framework instalado na máquina está na {v_canonica}. Agentes e roteador "
            f"são acoplados — rodar agentes novos contra roteamento antigo produz "
            f"decisão errada sem erro visível. Para sincronizar:\n"
            f"  cp $HOME/.claude-agent-framework/decide.py orchestrator/decide.py\n"
            f"  cp $HOME/.claude-agent-framework/VERSION  orchestrator/VERSION",
            file=sys.stderr,
        )


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

    if arquivo_atual == DONE and tarefa.get("documentado"):
        # Checado antes dos gatilhos: tarefa documentada está encerrada, e avaliar
        # divergência em cima dela reabriria trabalho fechado. Gap real no mesmo
        # componente continua sendo pego por qualquer tarefa viva dele.
        return {
            "acao": "nada_a_fazer",
            "motivo": f"Tarefa '{tarefa_id}' já está em done.md e documentada — "
                      f"ciclo encerrado, nada a fazer.",
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
    if len(sys.argv) > 2:
        print(json.dumps({
            "acao": "escalar_humano",
            "motivo": "Uso incorreto: o script de decisão espera no máximo um argumento, "
                      "o <tarefa_id>. Sem argumento, ele escolhe a próxima tarefa sozinho.",
        }, ensure_ascii=False))
        sys.exit(1)

    avisar_se_copia_local_desatualizada()

    try:
        if len(sys.argv) == 1:
            tarefa_id = proxima_tarefa()
            if tarefa_id is None:
                print(json.dumps({
                    "acao": "nada_a_fazer",
                    "motivo": "Nenhuma tarefa pendente em in-progress.md, done.md ou backlog.md.",
                }, ensure_ascii=False))
                return
            resultado = decidir(tarefa_id)
            # `tarefa_id` só aparece neste modo: quem chamou não sabe qual tarefa foi
            # escolhida. Na chamada com id explícito a saída fica byte a byte igual à
            # de antes da v1.1.0, para não quebrar nada que já leia esse JSON.
            resultado["tarefa_id"] = tarefa_id
        else:
            resultado = decidir(sys.argv[1])
    except EstadoMalformado as e:
        # Mesmo tratamento dado à ausência de pyyaml: JSON válido no stdout e
        # exit 1. A sessão principal precisa de um motivo reportável, não de um
        # traceback no stderr com stdout vazio.
        print(json.dumps({
            "acao": "escalar_humano",
            "motivo": f"Estado do projeto ilegível — {e}",
        }, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()
