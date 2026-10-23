r"""Robo de videos: produz 1 video por dia para qualquer canal (perfil em canais\<canal>\canal.json) e deixa na fila
para uma pessoa conferir e postar. Nao publica nada sozinho.

    python -m robo produzir [--canal arquivo-dark] [--sem-ia] [--forcar]
    python -m robo fila                      o que esta esperando aprovacao / postagem
    python -m robo aprovar <id>              conferido: pronto para postar
    python -m robo postado <id> <tiktok|youtube> <link>
    python -m robo custos                    chamadas de IA e custo estimado (hoje e total)
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
