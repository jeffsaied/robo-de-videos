r"""Robo de videos: produz 1 video por dia para qualquer canal (perfil em canais\<canal>\canal.json) e deixa na fila
para uma pessoa conferir e postar. Nao publica nada sozinho.

    python -m robo produzir [--canal arquivo-dark] [--sem-ia] [--forcar]
    python -m robo fila                      o que esta esperando aprovacao / postagem
    python -m robo aprovar <id>              conferido: pronto para postar
    python -m robo postado <id> <tiktok|youtube|instagram|facebook|kwai> <link>
    python -m robo custos                    chamadas de IA e custo estimado (hoje e total)
    python -m robo retencao <youtube_id> [--pasta <saida do video>]   onde as pessoas saem (curva da API)
    python -m robo placar [--canal X]        videos do canal por views/dia (o mesmo placar que pesa na escolha do tema)
"""
import json
import os
import sys

if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = 'robo'

from . import banco, ciclo  # noqa: E402


def _env():
    """Le o .env da raiz (segredos, como ANTHROPIC_API_KEY); nunca e impresso nem gravado no log."""
    arq = os.path.join(ciclo.RAIZ, '.env')
    if os.path.exists(arq):
        for linha in open(arq, encoding='utf-8-sig'):
            if '=' in linha and not linha.lstrip().startswith('#'):
                k, v = linha.strip().split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main(a):
    _env()
    if not a or a[0] in ('-h', '--help', 'ajuda'):
        print(__doc__)
        return
    cmd = a[0]
    c = banco.conectar()
    if cmd == 'produzir':
        canal = a[a.index('--canal') + 1] if '--canal' in a else ciclo.cfg().get('canal_padrao', 'arquivo-dark')
        ciclo.produzir(canal, sem_ia='--sem-ia' in a, forcar='--forcar' in a)
    elif cmd == 'fila':
        for r in c.execute("select id, canal, estado, tema, pasta, erro from execucoes where estado not in ('postado') order by id"):
            print(f'#{r["id"]} [{r["estado"]}] {r["canal"]}: {r["tema"] or "-"}\n    {r["pasta"] or r["erro"] or ""}')
    elif cmd == 'aprovar':
        c.execute("update execucoes set estado='aprovado' where id=? and estado='aguardando_aprovacao'", (int(a[1]),))
        c.commit()
        print('aprovado' if c.total_changes else 'nada mudou (id errado ou não estava aguardando aprovação)')
    elif cmd == 'postado':
        ex, onde, link = int(a[1]), a[2], a[3]
        c.execute('insert into postagens values (?,?,?,?)', (ex, onde, link, banco.agora()))
        ondes = {r['onde'] for r in c.execute('select onde from postagens where execucao=?', (ex,))}
        if {'tiktok', 'youtube'} <= ondes:
            c.execute("update execucoes set estado='postado' where id=?", (ex,))
        c.commit()
        print(f'registrado: #{ex} em {onde}')
    elif cmd == 'retencao':
        from . import retencao
        pasta = a[a.index('--pasta') + 1] if '--pasta' in a else None
        rel = retencao.relatorio(a[1], pasta)
        if 'erro' in rel:
            print(rel['erro'])
        else:
            print(f"chegam ao fim: {rel['chegam_ao_fim']:.0%} | comparado com vídeos parecidos: {rel['relativo_medio']} (0,5 = média)")
            for c in rel.get('maiores_quedas', []):
                print(f"  cena {c['cena']} ({c['inicio_s']} s) perde {c['perda_pct']}%: {c['texto']}")
    elif cmd == 'placar':
        from . import placar
        canal = a[a.index('--canal') + 1] if '--canal' in a else 'arquivo-dark'
        p = ciclo.perfil(canal)
        linhas = placar.resumo(p, os.path.join(ciclo.RAIZ, 'canais', canal))
        print(f'{"views/dia":>9} {"views":>7} {"like%":>6}  titulo')
        for v in linhas:
            print(f'{v["views_dia"]:>9} {v["views"]:>7} {v["like_pct"]:>6}  {v["titulo"][:70]}')
        if not linhas:
            print('sem numeros: rode o tendencias.py (ele grava os videos do canal em tendencias/)')
    elif cmd == 'custos':
        for titulo, filtro in (('hoje', "em like date('now','localtime') || '%'"), ('total', '1=1')):
            r = c.execute(f'select count(*) n, sum(cache) cache, coalesce(sum(custo_usd),0) s from chamadas_ia where {filtro}').fetchone()
            print(f'{titulo}: {r["n"]} chamadas ({r["cache"] or 0} do cache), custo estimado US$ {r["s"]:.3f}')
        for r in c.execute('select em, tarefa, provedor, modelo, tokens_entrada, tokens_saida, custo_usd, nota from chamadas_ia order by id desc limit 8'):
            print(f'  {r["em"]} {r["tarefa"]} {r["provedor"]}/{r["modelo"]} {r["tokens_entrada"]}+{r["tokens_saida"]} tok US$ {r["custo_usd"]:.3f} ({r["nota"]})')
    else:
        print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
