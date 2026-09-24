"""
Suite de regressao do roteamento de decide.py.

Rode da raiz do framework:  python3 tests/test_decide.py

Cada caso monta um projeto descartavel em diretorio temporario e chama
decide.py como subprocesso, do jeito que a sessao principal chama — sem
importar o modulo, para tambem cobrir o ponto de entrada e o formato de saida.

Os casos 1, 2, 6, 7 e 9 sao os que falhavam antes da correcao da v1.0.1;
nao remova nenhum deles sem entender o bug que cada um trava.
"""
import json, subprocess, sys, tempfile, textwrap
from pathlib import Path

DECIDE = str(Path(__file__).resolve().parent.parent / "decide.py")
falhas = []

total = 0

def rodar(nome, arquivos, tarefa_id, esperado, motivo_contem=None, campos=None,
          stderr_contem=None, stderr_vazio=False):
    """
    `tarefa_id=None` roda decide.py SEM argumento, exercitando a selecao
    automatica de tarefa (v1.1.0).

    `motivo_contem`: trecho que o campo `motivo` precisa conter. Existe para os
    casos de estado malformado, onde acertar a acao nao basta — o valor do
    tratamento esta em o motivo dizer QUAL arquivo esta torto.

    `campos`: dict de campo -> valor exato exigido no JSON de saida. Usado para
    travar o formato de arquivos_envolvidos e o tarefa_id escolhido.

    `stderr_contem` / `stderr_vazio`: os avisos de defasagem saem em stderr de
    proposito, para nao sujar o contrato do stdout. Travar os dois lados importa:
    o aviso precisa aparecer quando deve, e o JSON precisa seguir limpo.
    """
    global total
    total += 1
    with tempfile.TemporaryDirectory() as d:
        raiz = Path(d)
        for rel, conteudo in arquivos.items():
            alvo = raiz / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(textwrap.dedent(conteudo), encoding="utf-8")
        cmd = [sys.executable, DECIDE] + ([] if tarefa_id is None else [tarefa_id])
        out = subprocess.run(cmd, cwd=raiz, capture_output=True, text=True)
        err = out.stderr
        # json.loads falha alto de proposito: stdout vazio e a regressao que os
        # casos 17-19 travam, e ela nao deve passar por "esperado != obtido".
        got = json.loads(out.stdout)
    real = got.get("agente") or got.get("acao")
    ok = real == esperado
    if ok and motivo_contem is not None:
        ok = motivo_contem in got.get("motivo", "")
        if not ok:
            real = f"{real} (motivo sem {motivo_contem!r})"
    if ok and stderr_contem is not None and stderr_contem not in err:
        ok = False
        real = f"{real} (stderr sem {stderr_contem!r})"
    if ok and stderr_vazio and err.strip():
        ok = False
        real = f"{real} (stderr deveria estar vazio: {err.strip()[:60]!r})"
    if ok and campos:
        for campo, valor in campos.items():
            if got.get(campo) != valor:
                ok = False
                real = f"{real} ({campo}={got.get(campo)!r}, esperado {valor!r})"
                break
    marca = "ok  " if ok else "FALHA"
    if not ok:
        falhas.append((nome, esperado, real, got))
    print(f"{marca} {nome}: esperado={esperado} obtido={real}")

TAREFA_UI = """\
    - id: T-001
      componente: checkout
      tipo: ui
      specs_referenciadas:
        - docs/specs/functional/checkout.md
        - docs/specs/design/checkout.md
      status: pending
      gerado_por: planner
    """
FUNC = "versao: 1\n# Checkout\n"

# 1. spec de design ausente -> agente design (antes: orquestrador-llm)
rodar("design ausente", {
    "tasks/backlog.md": TAREFA_UI,
    "docs/specs/functional/checkout.md": FUNC,
}, "T-001", "design")

# 2. spec funcional ausente -> planner (antes: orquestrador-llm)
rodar("funcional ausente", {"tasks/backlog.md": TAREFA_UI}, "T-001", "planner")

# 3. todas as specs presentes -> implementador
rodar("specs completas", {
    "tasks/backlog.md": TAREFA_UI,
    "docs/specs/functional/checkout.md": FUNC,
    "docs/specs/design/checkout.md": "versao: 1\n",
}, "T-001", "implementador")

# 4. spec orfa (categoria sem dono) -> orquestrador-llm, gatilho preservado
rodar("spec orfa sem dono", {
    "tasks/backlog.md": """\
    - id: T-002
      componente: checkout
      tipo: ui
      specs_referenciadas:
        - docs/specs/legado/checkout.md
      status: pending
    """,
}, "T-002", "orquestrador-llm")

# 5. spec de design de OUTRO componente -> orfa -> orquestrador-llm
rodar("design de outro componente", {
    "tasks/backlog.md": """\
    - id: T-003
      componente: checkout
      tipo: ui
      specs_referenciadas:
        - docs/specs/functional/checkout.md
        - docs/specs/design/carrinho.md
      status: pending
    """,
    "docs/specs/functional/checkout.md": FUNC,
}, "T-003", "orquestrador-llm")

# 6. pipeline: data_pipeline com schema ausente -> data-pipeline
rodar("pipeline ausente", {
    "tasks/backlog.md": """\
    - id: T-004
      componente: ingestao
      tipo: data_pipeline
      specs_referenciadas:
        - docs/specs/functional/ingestao.md
        - docs/specs/data-pipeline/ingestao.md
        - docs/specs/qualification/ingestao.md
      requer_qualificacao: true
      status: pending
    """,
    "docs/specs/functional/ingestao.md": FUNC,
}, "T-004", "data-pipeline")

# 7. prioridade: schema presente, qualification ausente -> llm-qualification
rodar("prioridade qualification", {
    "tasks/backlog.md": """\
    - id: T-004
      componente: ingestao
      tipo: data_pipeline
      specs_referenciadas:
        - docs/specs/functional/ingestao.md
        - docs/specs/data-pipeline/ingestao.md
        - docs/specs/qualification/ingestao.md
      requer_qualificacao: true
      status: pending
    """,
    "docs/specs/functional/ingestao.md": FUNC,
    "docs/specs/data-pipeline/ingestao.md": "versao: 1\n",
}, "T-004", "llm-qualification")

# 8. rede de seguranca: requer_qualificacao sem listar a spec -> llm-qualification
rodar("rede de seguranca por tipo", {
    "tasks/backlog.md": """\
    - id: T-005
      componente: ingestao
      tipo: api
      specs_referenciadas:
        - docs/specs/functional/ingestao.md
      requer_qualificacao: true
      status: pending
    """,
    "docs/specs/functional/ingestao.md": FUNC,
}, "T-005", "llm-qualification")

# 9. circuit breaker: 3 decisoes INDEPENDENTES nao escalam (antes: escalava)
ORFA = """\
    - id: T-002
      componente: checkout
      tipo: ui
      specs_referenciadas:
        - docs/specs/legado/checkout.md
      status: pending
    """
rodar("3 decisoes independentes", {
    "tasks/backlog.md": ORFA,
    "docs/decisions/orchestrator/index.md": """\
    - id: 1
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
    - id: 2
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
    - id: 3
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
    """,
}, "T-002", "orquestrador-llm")

# 10. circuit breaker: cadeia real de 3 supersedes ESCALA
rodar("cadeia real de 3", {
    "tasks/backlog.md": ORFA,
    "docs/decisions/orchestrator/index.md": """\
    - id: 1
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
    - id: 2
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
      supersedes: 1
    - id: 3
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
      supersedes: 2
    """,
}, "T-002", "escalar_humano")

# 11. indice corrompido (ciclo) nao trava
rodar("indice ciclico", {
    "tasks/backlog.md": ORFA,
    "docs/decisions/orchestrator/index.md": """\
    - id: 1
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
      supersedes: 2
    - id: 2
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
      supersedes: 1
    """,
}, "T-002", "orquestrador-llm")

# 12. in-progress sem implementado -> implementador
rodar("in-progress pendente", {
    "tasks/in-progress.md": """\
    - id: T-010
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: doing
    """,
}, "T-010", "implementador")

# 13. in-progress com implementado -> revisor-qualidade
rodar("in-progress implementado", {
    "tasks/in-progress.md": """\
    - id: T-010
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      implementado: true
      status: doing
    """,
}, "T-010", "revisor-qualidade")

# 14. done -> documentador
rodar("done", {
    "tasks/done.md": """\
    - id: T-010
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: done
    """,
}, "T-010", "documentador")

# 15. travada 5 ciclos -> orquestrador-llm
rodar("travada 5 ciclos", {
    "tasks/in-progress.md": """\
    - id: T-010
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      ciclos_sem_progresso: 5
      status: doing
    """,
}, "T-010", "orquestrador-llm")

# 16. tarefa inexistente -> escalar_humano
rodar("tarefa inexistente", {"tasks/backlog.md": "[]\n"}, "T-999", "escalar_humano")

# ---------------------------------------------------------------------------
# 17-19. Contrato de saida no erro (v1.0.7). Antes: traceback e stdout vazio,
# que a docstring de decide.py contradizia ao prometer "sempre um destes tres
# formatos". Quem escreve esses arquivos e agente de LLM — YAML torto e cenario
# de operacao normal, nao corrupcao exotica.
# ---------------------------------------------------------------------------

# 17. lista de itens que nao sao mapeamentos -> escalar_humano nomeando o
# arquivo. Antes: AttributeError em `tarefa.get`, porque localizar_tarefa
# presumia dict em cada entrada.
rodar("backlog com itens nao-mapeamento", {
    "tasks/backlog.md": """\
    - T-001
    - T-002
    """,
}, "T-001", "escalar_humano", motivo_contem="tasks/backlog.md")

# 18. YAML sintaticamente invalido -> escalar_humano, nao AttributeError
rodar("backlog YAML invalido", {
    "tasks/backlog.md": "- id: T-001\n   componente: [checkout\n",
}, "T-001", "escalar_humano", motivo_contem="tasks/backlog.md")

# 19. indice de decisoes torto -> escalar_humano, e nao breaker falhando aberto.
# Usa a tarefa de spec orfa do caso 4 porque o indice so e lido quando algum
# gatilho dispara — com tarefa saudavel, profundidade_cadeia nem roda.
rodar("indice de decisoes torto", {
    "tasks/backlog.md": """\
    - id: T-002
      componente: checkout
      tipo: ui
      specs_referenciadas:
        - docs/specs/legado/checkout.md
      status: pending
    """,
    "docs/decisions/orchestrator/index.md": """\
    - id: 1
      gatilho: spec_ausente
      arquivos_envolvidos: docs/specs/legado/checkout.md
      status: resolved
    """,
}, "T-002", "escalar_humano", motivo_contem="index.md")

# ---------------------------------------------------------------------------
# 20-25. Selecao automatica de tarefa (P5, v1.1.0). Antes nao havia regra: o
# template mandava rodar "o proximo" e o script exigia um id, entao a escolha
# caia no julgamento da sessao — o oposto do principio do framework.
# ---------------------------------------------------------------------------

DUAS_FILAS = {
    "tasks/in-progress.md": """\
    - id: T-007
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: doing
    """,
    "tasks/backlog.md": """\
    - id: T-002
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: pending
    """,
}

# 20. in-progress vem antes de backlog, mesmo com id maior: terminar antes de comecar
rodar("sem argumento: in-progress antes de backlog", DUAS_FILAS,
      None, "implementador", campos={"tarefa_id": "T-007"})

# 21. ordenacao natural por id: T-2 antes de T-10 (ordem textual daria o contrario)
rodar("sem argumento: id ordenado como numero", {
    "tasks/backlog.md": """\
    - id: T-10
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: pending
    - id: T-2
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: pending
    """,
}, None, "planner", campos={"tarefa_id": "T-2"})

# 22. done sem documentar vem antes do backlog: fechar ciclo antes de abrir trabalho novo
rodar("sem argumento: done pendente antes de backlog", {
    "tasks/done.md": """\
    - id: T-050
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: done
    """,
    "tasks/backlog.md": """\
    - id: T-001
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: pending
    """,
}, None, "documentador", campos={"tarefa_id": "T-050"})

# 23. done JA documentado sai da fila — sem isso a selecao devolveria a mesma
# tarefa concluida para sempre, porque done.md sempre roteia para o documentador
rodar("sem argumento: done documentado sai da fila", {
    "tasks/done.md": """\
    - id: T-050
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: done
      documentado: true
    """,
}, None, "nada_a_fazer")

# 24. o mesmo pela chamada explicita por id
rodar("id explicito: done documentado", {
    "tasks/done.md": """\
    - id: T-050
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: done
      documentado: true
    """,
}, "T-050", "nada_a_fazer")

# 25. projeto sem nada pendente
rodar("sem argumento: nada pendente", {"tasks/backlog.md": "[]\n"},
      None, "nada_a_fazer")

# ---------------------------------------------------------------------------
# 26-27. Separador de caminho (P9). O circuit breaker compara
# arquivos_envolvidos por igualdade literal de string: separador dependente do
# SO fazia decisao gravada no Linux nunca casar com a mesma divergencia
# avaliada no Windows, e o breaker falhava ABERTO — nunca escalava.
# ---------------------------------------------------------------------------

# 26. o formato de saida e POSIX, travado
rodar("gap orfao devolve caminho POSIX", {
    "tasks/backlog.md": """\
    - id: T-001
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: pending
    """,
    "docs/specs/functional/checkout.md": FUNC,
    "docs/decisions/gap-reports/T-999.md": "componente: checkout\nstatus: divergente\n",
}, "T-001", "orquestrador-llm",
   campos={"arquivos_envolvidos": ["docs/decisions/gap-reports/T-999.md"]})

# 27. entrada antiga gravada com barra invertida ainda casa na leitura, senao
# toda cadeia de supersedes gravada no Windows reiniciaria do zero
rodar("indice com barra invertida ainda casa", {
    "tasks/backlog.md": ORFA,
    "docs/decisions/orchestrator/index.md": """\
    - id: 1
      gatilho: spec_ausente
      arquivos_envolvidos: ['docs\\specs\\legado\\checkout.md']
      status: resolved
    - id: 2
      gatilho: spec_ausente
      arquivos_envolvidos: ['docs\\specs\\legado\\checkout.md']
      status: resolved
      supersedes: 1
    - id: 3
      gatilho: spec_ausente
      arquivos_envolvidos: ['docs\\specs\\legado\\checkout.md']
      status: resolved
      supersedes: 2
    """,
}, "T-002", "escalar_humano")

# ---------------------------------------------------------------------------
# 28-30. Bloco do CLAUDE.md defasado (auditoria de 2026-09-24). O bloco carrega
# as instrucoes de fluxo que a sessao principal segue; quando fica para tras, o
# projeto ignora capacidade que o roteador ja tem, e nada acusava.
# ---------------------------------------------------------------------------

VERSAO_ATUAL = (Path(DECIDE).parent / "VERSION").read_text(encoding="utf-8").strip()
UMA_TAREFA = {
    "tasks/backlog.md": """\
    - id: T-001
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: pending
    """,
}
BLOCO = "<!-- BEGIN arquitetura-agentes-ia{} (gerado) -->\ntexto\n<!-- END arquitetura-agentes-ia -->\n"

# 28. bloco antigo -> aviso em stderr, stdout continua JSON limpo
rodar("bloco do CLAUDE.md defasado avisa", {**UMA_TAREFA, "CLAUDE.md": BLOCO.format(" v1.0.6")},
      "T-001", "planner", stderr_contem="v1.0.6")

# 29. bloco sem marca de versao (gerado antes da v1.2.0) tambem avisa
rodar("bloco sem marca de versao avisa", {**UMA_TAREFA, "CLAUDE.md": BLOCO.format("")},
      "T-001", "planner", stderr_contem="sem marca de versão")

# 30. bloco na versao corrente nao avisa — aviso que aparece sempre vira ruido
# e para de ser lido, que e o mesmo que nao existir
rodar("bloco atualizado nao avisa", {**UMA_TAREFA, "CLAUDE.md": BLOCO.format(" v" + VERSAO_ATUAL)},
      "T-001", "planner", stderr_vazio=True)

print()
print(f"{total - len(falhas)}/{total} passaram")
for nome, esp, real, got in falhas:
    print(f"  FALHA {nome}: esperado={esp} obtido={real} :: {got}")
sys.exit(1 if falhas else 0)
