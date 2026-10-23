"""Um ciclo de producao, em etapas que podem ser retomadas: pesquisar -> roteiro -> fatos -> montar -> conferir -> fila.
Cada etapa grava o resultado no banco; se o ciclo cair, o proximo comeca da etapa que faltou."""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date

from . import banco, ia, pesquisa

CODIGO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.environ.get('ROBO_DADOS') or CODIGO   # ROBO_DADOS: pasta de dados do app do robo
ROBO = os.path.join(RAIZ, 'robo')
sys.path.insert(0, CODIGO)


def log(ex, msg):
    linha = f'[{banco.agora()}] #{ex} {msg}'
    print(linha, flush=True)
    with open(os.path.join(ROBO, 'robo.log'), 'a', encoding='utf-8') as f:
        f.write(linha + '\n')


def cfg():
    return json.load(open(os.path.join(ROBO, 'robo.json'), encoding='utf-8'))


def perfil(canal):
    return json.load(open(os.path.join(RAIZ, 'canais', canal, 'canal.json'), encoding='utf-8'))


# ---------- 1. pesquisa e escolha (sem IA) ----------
def etapa_pesquisar(c, ex, canal, conf):
    usados = {r['chave'] for r in c.execute('select chave from temas where canal=?', (canal,))}
    fontes = perfil(canal).get('robo', {}).get('fontes', {})
    d = pesquisa.escolher(fontes, usados)
    if not d:
        raise RuntimeError('nenhum tema novo com texto e imagens livres suficientes nas fontes configuradas')
    c.execute('insert or replace into temas values (?,?,?,?,?)', (canal, d['chave'], d['titulo'], ex, banco.agora()))
    c.execute('update execucoes set tema=?, slug=? where id=?', (d['titulo'], d['chave'], ex))
    c.commit()
    log(ex, f'tema: {d["titulo"]} ({len(d["texto"])} letras, {len(d["imagens_livres"])} imagens livres)')
    return {'titulo': d['titulo'], 'chave': d['chave'], 'url': d['url'], 'texto': d['texto'][:9000], 'imagens': d['imagens_livres']}


# ---------- 2. roteiro (IA) ----------
PROMPT_ROTEIRO = """Você escreve roteiros de vídeos curtos (TikTok e YouTube Shorts, {min_s} a {max_s} segundos) em português do Brasil para o canal "{nome}", nicho: {nicho}.
Regras do canal:
{regras}

TEMA: {titulo}
FONTE (único material permitido; não use nada que não esteja aqui): {url}
TEXTO DA FONTE:
{texto}

IMAGENS DISPONÍVEIS (só estas; todas com licença livre já conferida):
{imagens}

Escreva UM roteiro original (não copie frases da fonte), com 14 a 18 cenas, 250 a 320 palavras no total.
Estrutura obrigatória:
{estrutura}
Sempre: datas, lugares e nomes só da fonte; separe fato confirmado de hipótese ("segundo relatos", "uma hipótese é");
1 frase de opinião do narrador; nada de citação entre aspas que não esteja na fonte; nada de número, data ou nome que não esteja na fonte.
Cada cena: "fala" (narração, números por extenso), "legenda" (a mesma fala escrita, com algarismos), "tela" (resumo curto), "imagem" (uma chave de "fontes"), "recorte" [0.5, 0.5, 1].
Use cada imagem em no máximo 4 cenas seguidas e escolha a imagem que mostra o que a cena fala.

Responda SÓ com JSON válido:
{{"titulo": "título curto", "post": "texto do post com uma pergunta no fim, até 300 caracteres", "hashtags": ["5 a 8 hashtags sem #"],
 "gancho": "texto curto do gancho", "fontes": {{"chave": {{"commons": "File:..."}}}}, "graficos": {{}},
 "cenas": [{{"fala": "", "legenda": "", "tela": "", "imagem": "chave", "recorte": [0.5, 0.5, 1]}}],
 "referencias": ["{url}"], "fatos": ["lista curta dos fatos usados"]}}"""

PROMPT_FATOS = """Confira o roteiro abaixo CONTRA a fonte. Aponte só problemas reais: fato que não está na fonte, número/data/nome errado,
hipótese dita como fato, citação inventada, gancho que afirma o que a fonte não afirma.
Confira UM POR UM cada ano, década, data, número e nome próprio da fala: a década tem de bater com o ano da fonte
(ex.: um filme de 1995 não é "dos anos oitenta"). Na dúvida, aponte.
FONTE:
{texto}

ROTEIRO (falas):
{falas}

Responda SÓ com JSON: {{"ok": true/false, "problemas": ["cena N: problema e correção"]}}"""


PADRAO_ESTRUTURA = [
    'Os 2 primeiros segundos prendem pela CURIOSIDADE (a afirmação mais estranha e verdadeira do caso, sem introdução).',
    'O meio se desenvolve SEM entregar a resposta: cada frase cria expectativa.',
    'A resposta (o dado mais importante) só no FINAL. Logo antes dela, um CTA de uma frase: "{cta}". Depois vem a resposta.',
]


def estrutura(p):
    """A estrutura vem do perfil do canal (estrutura_roteiro / cta_padrao); sem ela, vale a padrao acima."""
    cta = p.get('cta_padrao', 'Se inscreve no canal, que a resposta vem agora.')
    itens = p.get('estrutura_roteiro') or PADRAO_ESTRUTURA
    if isinstance(itens, str):
        itens = [itens]
    return '\n'.join('- ' + str(x).replace('{cta}', cta) for x in itens) + f'\n- CTA a usar: "{cta}"'


def etapa_roteiro(c, ex, canal, conf, dossie, ajuste=''):
    p = perfil(canal)
    imagens = '\n'.join(f'- {k} | {v["descricao"] or "(sem descrição)"} | {v["licenca"]}' for k, v in dossie['imagens'].items())
    prompt = PROMPT_ROTEIRO.format(min_s=p.get('tiktok', {}).get('segundos_min', 61), max_s=p.get('tiktok', {}).get('segundos_max', 120),
                                   nome=p['nome'], nicho=p.get('nicho', ''), regras='\n'.join('- ' + r for r in p.get('regras_roteiro', [])),
                                   titulo=dossie['titulo'], url=dossie['url'], texto=dossie['texto'], imagens=imagens,
                                   estrutura=estrutura(p))
    if ajuste:
        prompt += '\n\nCORRIJA ESTES PROBLEMAS apontados na conferência anterior:\n' + ajuste
    rot = ia.json_da_resposta(ia.chamar(c, conf['ia'], ex, 'roteiro', prompt))
    # so imagens da lista conferida; cenas com imagem desconhecida caem na primeira valida
    validas = {k: v for k, v in rot.get('fontes', {}).items() if v.get('commons') in dossie['imagens']}
    if not validas:
        raise RuntimeError('o roteiro não usou nenhuma das imagens conferidas')
    for k, v in validas.items():
        v['autor'] = dossie['imagens'][v['commons']]['autor'] or None
        if v['autor'] is None:
            v.pop('autor')
    rot['fontes'] = validas
    primeira = next(iter(validas))
    for cena in rot['cenas']:
        cena.pop('grafico', None)
        if cena.get('imagem') not in validas:
            cena['imagem'] = primeira
    rot['graficos'] = {}
    return rot


def etapa_fatos(c, ex, canal, conf, dossie, rot):
    falas = '\n'.join(f'cena {i + 1}: {x["fala"]}' for i, x in enumerate(rot['cenas']))
    j = ia.json_da_resposta(ia.chamar(c, conf['ia'], ex, 'conferir_fatos', PROMPT_FATOS.format(texto=dossie['texto'], falas=falas)))
    return j


# ---------- 3. montagem (sem IA): o gerador que ja existe ----------
def etapa_montar(c, ex, canal, roteiro_id):
    # no app (.exe) a fabrica roda pelo proprio executavel
    cmd = [sys.executable, '--fabrica'] if getattr(sys, 'frozen', False) else [sys.executable, os.path.join(CODIGO, 'fabrica_tiktok.py')]
    r = subprocess.run(cmd + [canal, roteiro_id],
                       capture_output=True, text=True, encoding='utf-8', cwd=RAIZ, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError('fabrica_tiktok falhou: ' + (r.stderr or r.stdout)[-600:])
    return os.path.join(RAIZ, 'canais', canal, 'saida', 'tiktok_' + roteiro_id)


# ---------- 4. conferencia tecnica e editorial (sem IA) ----------
def etapa_conferir(canal, pasta, rot):
    p = perfil(canal)
    final = os.path.join(pasta, 'final.mp4')
    pr = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,width,height',
                                    '-of', 'json', final], capture_output=True, text=True).stdout)
    dur = float(pr['format']['duration'])
    video = [s for s in pr['streams'] if s['codec_type'] == 'video'][0]
    tem_audio = any(s['codec_type'] == 'audio' for s in pr['streams'])
    creditos = json.load(open(os.path.join(pasta, 'creditos.json'), encoding='utf-8'))
    vigiar = [w for w in p.get('palavras_vigiar', []) if re.search(r'\b' + re.escape(w) + r'\b', ' '.join(x['fala'] for x in rot['cenas']), re.I)]
    t = p.get('tiktok', {})
    problemas = []
    if not (t.get('segundos_min', 0) <= dur <= t.get('segundos_max', 1e9)):
        problemas.append(f'duração {dur:.1f}s fora da faixa {t.get("segundos_min")}-{t.get("segundos_max")}s')
    if (video['width'], video['height']) != (1080, 1920):
        problemas.append(f'resolução {video["width"]}x{video["height"]}')
    if not tem_audio:
        problemas.append('sem áudio')
    if os.path.getsize(final) > 280e6:
        problemas.append('arquivo maior que 280 MB')
    if not creditos:
        problemas.append('sem créditos de imagem')
    if any(re.search(r'\bNC\b|NonCommercial', x.get('licenca', ''), re.I) for x in creditos):
        problemas.append('imagem com licença NC')
    if vigiar:
        problemas.append('palavras a conferir na fala: ' + ', '.join(vigiar))
    # pronuncia (faster-whisper) e volume final: avisos para quem aprova, nao travam a fila
    from robo import conferencias
    lufs = conferencias.volume(final)
    if lufs is None or abs(lufs + 14) > 1.5:
        problemas.append(f'volume {lufs} LUFS (alvo -14)')
    pasta_canal = os.path.dirname(os.path.dirname(os.path.abspath(pasta)))   # canais\<canal>\saida\<video> -> canais\<canal>
    for img, antes in conferencias.repetidas(pasta, pasta_canal):
        problemas.append(f'imagem {img} já apareceu em {antes} (trocar para não parecer template)')
    textos = conferencias.texto_nas_imagens(pasta, rot)          # None = Tesseract nao instalado neste PC
    for cena, txt in textos or []:
        problemas.append(f'texto dentro da imagem da cena {cena}: "{txt}" (rótulo em inglês ou cortado? recortar ou trocar)')
    try:
        pron = conferencias.pronuncia(pasta, rot)
    except Exception as e:                           # sem whisper ou audio estranho: avisa e segue
        pron = {'feito': False, 'motivo': str(e), 'suspeitos': []}
    if pron['suspeitos']:
        problemas.append('ouvir a pronúncia de: ' + ', '.join(f"{x['nome']} (cena {x['cena']})" for x in pron['suspeitos']))
    elif not pron['feito']:
        problemas.append('pronúncia não conferida: ' + pron.get('motivo', ''))
    return {'duracao': round(dur, 1), 'problemas': problemas, 'creditos': creditos,
            'lufs': lufs, 'pronuncia': pron.get('suspeitos', []), 'transcricao': pron.get('transcricao', '')}


# ---------- 5. fila para a pessoa postar (sem IA) ----------
def etapa_fila(c, ex, canal, pasta, rot, dossie, conferencia):
    destino = os.path.join(ROBO, 'fila', f'{date.today().isoformat()}_{canal}_{dossie["chave"]}')
    os.makedirs(destino, exist_ok=True)
    shutil.copy2(os.path.join(pasta, 'final.mp4'), os.path.join(destino, 'video.mp4'))
    shutil.copy2(os.path.join(pasta, 'tira_quadros.png'), os.path.join(destino, 'conferir_quadros.png'))
    legenda = open(os.path.join(pasta, 'legenda.txt'), encoding='utf-8').read()
    hashtags = ' '.join('#' + h for h in rot.get('hashtags', []))
    open(os.path.join(destino, 'tiktok_legenda.txt'), 'w', encoding='utf-8').write(legenda)
    open(os.path.join(destino, 'hashtags.txt'), 'w', encoding='utf-8').write(hashtags + '\n')
    titulo = rot['titulo'][:95] + ' #shorts'
    open(os.path.join(destino, 'youtube.txt'), 'w', encoding='utf-8').write(
        f'TÍTULO:\n{titulo}\n\nDESCRIÇÃO:\n{legenda}\n\nTAGS:\n{", ".join(rot.get("hashtags", []))}\n')
    refs = rot.get('referencias') or [dossie['url']]
    open(os.path.join(destino, 'fontes.txt'), 'w', encoding='utf-8').write(
        'REFERÊNCIAS DO ROTEIRO:\n' + '\n'.join(refs) + '\n\nIMAGENS (licença e autor):\n' +
        '\n'.join(f'- {x.get("titulo") or x.get("arquivo")} | {x.get("licenca")} | {x.get("autor")} | {x.get("url", "")}' for x in conferencia['creditos']) + '\n')
    for x in conferencia['creditos']:
        c.execute('insert into midias values (?,?,?,?,?)', (ex, x.get('titulo') or x.get('arquivo'), x.get('autor'), x.get('licenca'), x.get('url')))
    aviso = ('\nATENÇÃO, conferir antes de postar:\n- ' + '\n- '.join(conferencia['problemas'])) if conferencia['problemas'] else ''
    open(os.path.join(destino, 'LEIA.txt'), 'w', encoding='utf-8').write(
        f'Vídeo: {rot["titulo"]} ({conferencia["duracao"]} s)\n'
        '1. Assista o video.mp4 (ou olhe conferir_quadros.png).\n'
        '2. TikTok: suba o video.mp4 e cole o tiktok_legenda.txt; escolha cada hashtag na lista que aparece ao digitar.\n'
        '3. YouTube Shorts: use o título, a descrição e as tags do youtube.txt.\n'
        '4. Depois de postar: python -m robo postado ' + str(ex) + ' tiktok <link>   (e o mesmo para youtube)\n' + aviso + '\n')
    c.commit()
    return destino


# ---------- o ciclo ----------
def produzir(canal, sem_ia=False, forcar=False):
    conf = cfg()
    if sem_ia:
        conf['ia']['ligada'] = False
    c = banco.conectar()
    banco.travar()
    try:
        aberta = c.execute("select * from execucoes where canal=? and estado in ('rodando','falhou') order by id desc limit 1", (canal,)).fetchone()
        hoje = c.execute("select count(*) n from execucoes where canal=? and inicio like ? and estado not in ('rodando','falhou')",
                         (canal, date.today().isoformat() + '%')).fetchone()['n']
        if not aberta and conf.get('videos_por_dia', 0) and hoje >= conf['videos_por_dia'] and not forcar:
            print(f'já há {hoje} vídeo(s) de hoje para "{canal}" (limite {conf.get("videos_por_dia", 1)}). Use --forcar para outro.')
            return None
        if aberta:
            ex = aberta['id']
            c.execute("update execucoes set estado='rodando', erro=null where id=?", (ex,))
            log(ex, 'retomando execução')
        else:
            ex = c.execute("insert into execucoes (canal, inicio, estado) values (?,?,'rodando')", (canal, banco.agora())).lastrowid
            log(ex, f'nova execução para o canal "{canal}"')
        c.commit()
        try:
            dossie = banco.etapa_feita(c, ex, 'pesquisar') or etapa_pesquisar(c, ex, canal, conf)
            banco.marcar_etapa(c, ex, 'pesquisar', 'ok', dossie)
            roteiro_id = 'robo_' + dossie['chave'][:40]
            rot = banco.etapa_feita(c, ex, 'roteiro')
            if not rot:
                try:
                    rot = etapa_roteiro(c, ex, canal, conf, dossie)
                    for tentativa in range(conf.get('tentativas_fatos', 1) + 1):
                        f = etapa_fatos(c, ex, canal, conf, dossie, rot)
                        if f.get('ok') or not f.get('problemas'):
                            break
                        log(ex, f'conferência de fatos achou {len(f["problemas"])} problema(s); corrigindo')
                        if tentativa < conf.get('tentativas_fatos', 1):
                            rot = etapa_roteiro(c, ex, canal, conf, dossie, ajuste='\n'.join(f['problemas']))
                    rot['conferencia_fatos'] = f
                except ia.SemOrcamento as e:
                    c.execute("update execucoes set estado='precisa_roteiro', erro=? where id=?", (str(e), ex))
                    c.commit()
                    pasta_d = os.path.join(ROBO, 'fila', f'{date.today().isoformat()}_{canal}_{dossie["chave"]}_SEM_ROTEIRO')
                    os.makedirs(pasta_d, exist_ok=True)
                    json.dump(dossie, open(os.path.join(pasta_d, 'dossie.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
                    log(ex, f'parado sem IA ({e}); dossiê em {pasta_d}')
                    return pasta_d
                arq = os.path.join(RAIZ, 'canais', canal, 'roteiros', roteiro_id + '.json')
                os.makedirs(os.path.dirname(arq), exist_ok=True)
                json.dump(rot, open(arq, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
                banco.marcar_etapa(c, ex, 'roteiro', 'ok', rot)
                log(ex, f'roteiro pronto: {len(rot["cenas"])} cenas')
            pasta = banco.etapa_feita(c, ex, 'montar') or etapa_montar(c, ex, canal, roteiro_id)
            banco.marcar_etapa(c, ex, 'montar', 'ok', pasta)
            confer = etapa_conferir(canal, pasta, rot)
            banco.marcar_etapa(c, ex, 'conferir', 'ok', confer)
            log(ex, f'conferência: {confer["duracao"]}s, problemas: {confer["problemas"] or "nenhum"}')
            destino = etapa_fila(c, ex, canal, pasta, rot, dossie, confer)
            c.execute("update execucoes set estado='aguardando_aprovacao', fim=?, pasta=? where id=?", (banco.agora(), destino, ex))
            c.commit()
            log(ex, f'na fila para aprovação: {destino}')
            return destino
        except Exception as e:
            c.execute("update execucoes set estado='falhou', erro=? where id=?", (str(e)[:500], ex))
            c.commit()
            log(ex, f'FALHOU: {e}')
            raise
    finally:
        banco.destravar()
        c.close()
