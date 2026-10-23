r"""Gera um video de TikTok (9:16, 1-3 min) a partir de um roteiro em arquivo e do perfil do canal.

    python fabrica_tiktok.py <canal> <roteiro>     ex.: python fabrica_tiktok.py arquivo-dark oumuamua

Le canais/<canal>/canal.json e canais/<canal>/roteiros/<roteiro>.json; sai em canais/<canal>/saida/tiktok_<roteiro>/:
final.mp4, legenda.txt (texto do post com creditos gerados das fichas), creditos.json e tira_quadros.png (teste mudo).

Roteiro: cada cena tem "fala" (o que a voz le, numeros por extenso), "tela" (o que a legenda mostra), e "imagem"
(chave em "fontes", com "recorte" [centro x, centro y, altura visivel] e, opcional, "marcador" {"seta": [x, y] na
foto, "rotulo": "..."}) OU "grafico" (chave em "graficos", dados
reais). Fonte com "ilustracao": true ganha o selo ILUSTRACAO na tela. "destaque" pinta a legenda de alerta; "pausa" deixa a pausa longa da voz no fim da cena.
"""
import json
import os
import re
import subprocess
import sys
import unicodedata
import wave
from difflib import SequenceMatcher

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import canal                      # montagem por cena (zoom + legendas) reaproveitada
import graficos
from motores import imagens, voz

AQUI = os.environ.get('ROBO_DADOS') or os.path.dirname(os.path.abspath(__file__))
LARG, ALT, FPS = canal.LARG, canal.ALT, canal.FPS
ATRASO = 0.35                     # respiro antes da 1a palavra


def ffmpeg(*args):
    canal.ffmpeg(*args)


def carregar(canal_id, roteiro_id):
    pasta_canal = os.path.join(AQUI, 'canais', canal_id)
    perfil = json.load(open(os.path.join(pasta_canal, 'canal.json'), encoding='utf-8'))
    perfil['_pasta'] = pasta_canal
    rot = json.load(open(os.path.join(pasta_canal, 'roteiros', roteiro_id + '.json'), encoding='utf-8'))
    for i, c in enumerate(rot['cenas']):
        if not c.get('fala') or not c.get('tela') or bool(c.get('imagem')) == bool(c.get('grafico')):
            raise ValueError(f'cena {i}: precisa de fala, tela e (imagem OU grafico)')
        if c.get('imagem') and c['imagem'] not in rot['fontes']:
            raise ValueError(f'cena {i}: imagem "{c["imagem"]}" nao esta em fontes')
        if c.get('grafico') and c['grafico'] not in rot['graficos']:
            raise ValueError(f'cena {i}: grafico "{c["grafico"]}" nao esta em graficos')
    return perfil, rot


def _rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def legenda_png(texto, destino, perfil, destaque=False):
    """Uma linha de legenda (os blocos ja vem cortados para caber)."""
    v = perfil['visual']
    fonte = ImageFont.truetype(v['fonte_titulo'], 122 if destaque else 96)
    img = Image.new('RGBA', (LARG, 420), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    linha = texto.upper()
    while d.textlength(linha, font=fonte) > LARG - 120 and fonte.size > 60:   # cabe numa linha
        fonte = ImageFont.truetype(v['fonte_titulo'], fonte.size - 4)
    cor = _rgb(v['alerta']) if destaque else _rgb(v['destaque'])
    x = (LARG - d.textlength(linha, font=fonte)) // 2
    d.text((x, (420 - fonte.size) // 2 - 10), linha, font=fonte, fill=cor, stroke_width=8, stroke_fill=(0, 0, 0))
    sombra = img.split()[3].filter(ImageFilter.GaussianBlur(14)).point(lambda a: a * 0.6)
    fundo = Image.new('RGBA', img.size, (0, 0, 0, 0))
    fundo.putalpha(sombra)
    Image.alpha_composite(fundo, img).save(destino)


def selo(img_path, texto, perfil):
    """Etiqueta no canto de cima (dentro da area que o zoom nao corta) para concepcao artistica nao passar por foto."""
    img = Image.open(img_path).convert('RGB')
    d = ImageDraw.Draw(img, 'RGBA')
    f = ImageFont.truetype(perfil['visual']['fonte_texto_negrito'], 48)
    w = d.textlength(texto, font=f)
    x, y = 110, 150                                   # canto esquerdo: o direito fica sob as abas do TikTok
    d.rounded_rectangle([x - 20, y - 8, x + w + 20, y + 66], 12, fill=(0, 0, 0, 200))
    d.text((x, y), texto, font=f, fill=(255, 255, 255))
    img.save(img_path, quality=95)


NEGACOES = {'nao', 'nem', 'nunca', 'sem'}


def selo_png(png, texto, perfil):
    """Etiqueta centralizada num png transparente (ex.: rotulo do som real no gancho)."""
    img = Image.open(png).convert('RGBA')
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(perfil['visual']['fonte_texto_negrito'], 46)
    w = d.textlength(texto, font=f)
    x = (LARG - w) / 2
    d.rounded_rectangle([x - 22, 20, x + w + 22, 96], 12, fill=(0, 0, 0, 210))
    d.text((x, 28), texto, font=f, fill=_rgb(perfil['visual']['destaque']))
    img.save(png)


def blocos_tela(texto, limite):
    """Blocos de 1 linha (ate `limite` letras, ate 3 palavras), fechando na pontuacao; 1 palavra nao fica sozinha."""
    blocos, atual = [], []
    for p in texto.split():
        if len(atual) >= 2 and (len(' '.join(atual + [p])) > limite or len(atual) == 3):   # 2 a 3 palavras
            blocos.append(atual)
            atual = []
        atual.append(p)
        if p[-1] in '.:?!,' and len(atual) >= 2:
            blocos.append(atual)
            atual = []
    if atual:
        blocos.append(atual)
    # negacao nunca fecha um bloco: sem som, "...NAO" / "HA CRATERA." inverte o sentido
    for k in range(len(blocos) - 1):
        while len(blocos[k]) > 1 and _norm(blocos[k][-1]) in NEGACOES:
            blocos[k + 1].insert(0, blocos[k].pop())
        if len(blocos[k]) == 1:                          # sobrou 1 palavra: vai junto (a legenda encolhe a fonte)
            blocos[k + 1] = blocos[k] + blocos[k + 1]
            blocos[k] = []
    blocos = [b for b in blocos if b]
    if len(blocos) > 1 and len(blocos[-1]) == 1:
        if len(' '.join(blocos[-2] + blocos[-1])) <= limite + 4 or len(blocos[-2]) < 3:
            ultimo = blocos.pop()
            blocos[-1] += ultimo
        else:
            blocos[-1].insert(0, blocos[-2].pop())
    # mais de 3 palavras: a ultima passa para o bloco seguinte (sem deixar negacao no fim); o ultimo bloco se divide
    k = 0
    while k < len(blocos):
        while len(blocos[k]) > 3 and (k + 1 < len(blocos) or len(blocos[k]) >= 4):
            if k + 1 == len(blocos):
                meio = len(blocos[k]) // 2
                blocos[k:k + 1] = [blocos[k][:meio], blocos[k][meio:]]
                break
            blocos[k + 1].insert(0, blocos[k].pop())
            while len(blocos[k]) > 1 and _norm(blocos[k][-1]) in NEGACOES:
                blocos[k + 1].insert(0, blocos[k].pop())
        k += 1
    # conferencia final da negacao (as regras acima podem ter mexido nas bordas): junta com o bloco seguinte
    for k in range(len(blocos) - 1):
        if blocos[k] and _norm(blocos[k][-1]) in NEGACOES:
            if len(blocos[k]) <= 2:                      # "Mas nao" + "havia cauda." -> "Mas nao havia cauda."
                blocos[k + 1] = blocos[k] + blocos[k + 1]
                blocos[k] = []
            else:
                blocos[k + 1].insert(0, blocos[k].pop())
    return [' '.join(b) for b in blocos if b]


def recortar(origem, cx, cy, hf, destino):
    img = Image.open(origem).convert('RGB')
    w, h = img.size
    ch = hf * h
    cw = min(ch * LARG / ALT, w)
    ch = cw * ALT / LARG
    x = min(max(cx * w - cw / 2, 0), w - cw)
    y = min(max(cy * h - ch / 2, 0), h - ch)
    img.crop((round(x), round(y), round(x + cw), round(y + ch))).resize((LARG, ALT), Image.LANCZOS).save(destino, quality=95)
    return lambda sx, sy: ((sx * w - x) / cw * LARG, (sy * h - y) / ch * ALT)   # ponto da foto -> ponto da tela


def marcador(img_path, ponto, texto, perfil):
    """Seta + rotulo apontando o que importa numa foto real confusa (ex.: o ponto que e o objeto, nao o traco)."""
    img = Image.open(img_path).convert('RGB')
    d = ImageDraw.Draw(img, 'RGBA')
    px, py = ponto
    cor = _rgb(perfil['visual']['destaque'])
    d.ellipse([px - 70, py - 70, px + 70, py + 70], outline=cor, width=7)
    x0, y0 = px + 200, py - 260                                   # seta vem de cima, pela direita
    d.line([(x0, y0), (px + 55, py - 55)], fill=cor, width=8)
    d.polygon([(px + 50, py - 50), (px + 95, py - 62), (px + 62, py - 95)], fill=cor)
    f = ImageFont.truetype(perfil['visual']['fonte_texto_negrito'], 50)
    w = d.textlength(texto, font=f)
    tx = min(max(x0 - w / 2, 110), LARG - 110 - w)
    d.rounded_rectangle([tx - 20, y0 - 80, tx + w + 20, y0 - 10], 12, fill=(0, 0, 0, 190))
    d.text((tx, y0 - 76), texto, font=f, fill=cor)
    img.save(img_path, quality=95)


def texto_para_voz(cenas):
    """A pontuacao real fica (a voz termina cada frase com a entonacao certa); o silencio comprido que a voz
    poe depois do ponto e encurtado depois, no audio (encurtar_pausas)."""
    partes = []
    for c in cenas:
        f = c['fala'].strip()
        partes.append(f if f[-1] in '.!?,;:' else f + '.')
    return ' '.join(partes)


def _norm(w):
    w = unicodedata.normalize('NFD', w.lower())
    return ''.join(ch for ch in w if ch.isalnum())


def alinhar_blocos(textos, pc):
    """Inicio de cada bloco de tela = tempo da palavra falada que corresponde a ele (casamento de palavras,
    sem acento/pontuacao). Blocos so com numero ("2019") nao casam com a fala ("dois mil e dezenove"):
    esses ficam no meio entre os vizinhos que casaram."""
    tokens = [(bi, _norm(t)) for bi, b in enumerate(textos) for t in b.split()]
    sm = SequenceMatcher(None, [t for _, t in tokens], [_norm(w) for w, _, _ in pc], autojunk=False)
    casou = {}
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            casou.setdefault(tokens[a + k][0], pc[b + k][1])
    inicios = [casou.get(bi) for bi in range(len(textos))]
    inicios[0] = pc[0][1]                            # o 1o bloco entra junto com a 1a palavra da cena
    fim = pc[-1][2]
    for bi in range(len(textos)):                    # preenche os que nao casaram
        if inicios[bi] is None:
            ant = inicios[bi - 1]
            prox = next((x for x in inicios[bi + 1:] if x is not None), fim)
            faltam = next((k for k, x in enumerate(inicios[bi + 1:], 1) if x is not None), len(textos) - bi)
            inicios[bi] = ant + (prox - ant) / (faltam + 1)
    for bi in range(1, len(inicios)):                # sempre em ordem, cada bloco pelo menos 0,3 s na tela
        inicios[bi] = max(inicios[bi], inicios[bi - 1] + 0.3)
    return inicios


def casar_palavras(voz_pal, roteiro):
    """Um tempo para cada palavra do roteiro, a partir das palavras que a voz marcou. As que nao casam
    (ex.: a voz leu "oito quatro" como um bloco so) ficam espalhadas entre as vizinhas que casaram."""
    sm = SequenceMatcher(None, [_norm(w) for w in roteiro], [_norm(w) for w, _, _ in voz_pal], autojunk=False)
    tempos = [None] * len(roteiro)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            tempos[a + k] = voz_pal[b + k][1:]
    if tempos[0] is None:
        tempos[0] = voz_pal[0][1:]
    if tempos[-1] is None:
        tempos[-1] = voz_pal[-1][1:]
    i = 0
    while i < len(tempos):
        if tempos[i] is None:
            j = i
            while tempos[j] is None:
                j += 1
            ini, fim = tempos[i - 1][1], tempos[j][0]
            passo = (fim - ini) / (j - i)
            for k in range(i, j):
                tempos[k] = (ini + passo * (k - i), ini + passo * (k - i + 1))
            i = j
        i += 1
    return [(w, a, b) for w, (a, b) in zip(roteiro, tempos)]


def encurtar_pausas(wav, palavras, cenas, fim_frase=0.32, meio=0.16, pausa_longa=0.7):
    """Deixa a fala corrida e natural: cada silencio entre palavras vira no maximo `fim_frase` (depois de . ! ?),
    `meio` (dentro da frase) ou `pausa_longa` (cena marcada com "pausa"); os tempos das palavras andam junto."""
    alvo = []
    for c in cenas:
        f = c['fala']
        ms = list(re.finditer(r'\w+', f))
        for k, m in enumerate(ms):
            resto = f[m.end():m.end() + 2]
            if k == len(ms) - 1 and c.get('pausa'):
                alvo.append(pausa_longa)
            elif re.match(r'\s*[.!?]', resto):
                alvo.append(fim_frase)
            else:
                alvo.append(meio)
    import numpy as np
    with wave.open(wav) as w:
        taxa, params = w.getframerate(), w.getparams()
        som = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2')
    pedacos, novas, desloc, corte = [], [], 0.0, 0
    for i, (txt, a, b) in enumerate(palavras):
        novas.append((txt, a - desloc, b - desloc))
        if i + 1 >= len(palavras):
            break
        lacuna = palavras[i + 1][1] - b
        limite = alvo[i] if i < len(alvo) else meio
        if lacuna > limite + 0.02:
            tirar = lacuna - limite
            # corta no meio do silencio, longe do fim da palavra (o "rabo" da voz termina) e do comeco da proxima
            ini = int((b + limite / 2) * taxa)
            fim = ini + int(tirar * taxa)
            pedacos.append(som[corte:ini].astype(np.float32))
            corte = fim
            desloc += tirar
    pedacos.append(som[corte:].astype(np.float32))
    # cada emenda ganha uma passagem suave de 25 ms (sai baixando, entra subindo): sem isso o corte seco fazia um "toc" oco
    n = int(0.025 * taxa)
    for k in range(len(pedacos)):
        if k + 1 < len(pedacos) and len(pedacos[k]) > n:
            pedacos[k][-n:] *= np.linspace(1, 0, n)
        if k > 0 and len(pedacos[k]) > n:
            pedacos[k][:n] *= np.linspace(0, 1, n)
    with wave.open(wav, 'wb') as w:
        w.setparams(params)
        w.writeframes(np.clip(np.concatenate(pedacos), -32768, 32767).astype('<i2').tobytes())
    return novas


def tira(video, destino, total):
    linhas = max(1, -(-int(total / 2.5 + 1) // 8))   # cabe o video inteiro, 1 quadro a cada 2,5 s
    ffmpeg('-i', video, '-vf', f'fps=1/2.5,scale=216:384,tile=8x{linhas}', '-frames:v', '1', destino)


def vigiar(perfil, rot):
    """Avisa (nao trava) quando o gancho ou a tela usam palavras que costumam afirmar mais do que se sabe.
    As regras ficam no perfil (regras_roteiro); quem decide se a palavra cabe e a revisao."""
    vig = perfil.get('palavras_vigiar', [])
    textos = [('gancho', rot.get('gancho', ''))] + [(f'cena {i} legenda', c.get('legenda') or c['tela']) for i, c in enumerate(rot['cenas'])]
    for onde, t in textos:
        achou = [w for w in vig if re.search(r'\b' + re.escape(w) + r'\b', t, re.I)]
        if achou:
            print(f'conferir ({onde}): {", ".join(achou)} -> "{t}"')


def gerar(canal_id, roteiro_id):
    perfil, rot = carregar(canal_id, roteiro_id)
    vigiar(perfil, rot)
    graficos.usar(perfil)
    pasta = os.path.join(perfil['_pasta'], 'saida', 'tiktok_' + roteiro_id)
    fontes_dir = os.path.join(pasta, 'fontes')
    os.makedirs(fontes_dir, exist_ok=True)
    cenas = rot['cenas']

    # 1. imagens reais (com ficha de credito) e graficos proprios
    creditos = {}
    usadas = {c['imagem'] for c in cenas if c.get('imagem')}
    usadas |= {g['fonte'] for g in rot.get('graficos', {}).values() if g.get('fonte')}   # grafico feito a partir de arquivo
    arq_fonte = lambda k: os.path.join(fontes_dir, k + ('.ogg' if rot['fontes'][k].get('audio') else '.jpg'))
    som = rot.get('som_gancho')
    if som:
        usadas.add(som['fonte'])
    for chave in usadas:
        creditos[chave] = imagens.baixar(rot['fontes'][chave], arq_fonte(chave))
    atraso = ATRASO + (som['duracao'] if som else 0)   # com som real no gancho, a voz entra depois dele
    for i, c in enumerate(cenas):
        destino = os.path.join(pasta, f'img{i}.jpg')
        if c.get('grafico'):
            spec = dict(rot['graficos'][c['grafico']])
            if spec.get('fonte'):
                spec['arquivo'] = arq_fonte(spec.pop('fonte'))
            graficos.desenhar(spec, destino)
        else:
            para_tela = recortar(os.path.join(fontes_dir, c['imagem'] + '.jpg'), *c['recorte'], destino)
            if c.get('marcador'):
                marcador(destino, para_tela(*c['marcador']['seta']), c['marcador']['rotulo'], perfil)
            if rot['fontes'][c['imagem']].get('ilustracao') or creditos[c['imagem']].get('ilustracao'):   # roteiro OU Commons
                selo(destino, 'ILUSTRAÇÃO', perfil)
            elif rot['fontes'][c['imagem']].get('selo'):              # ex.: "OUTRO BÓLIDO, 2020" em foto de outro evento
                selo(destino, rot['fontes'][c['imagem']]['selo'], perfil)

    # 2. voz numa tirada so, com o tempo de cada palavra
    wav, palavras = voz.narrar(texto_para_voz(cenas), perfil, pasta)
    contagem = [len(re.findall(r'\w+', c['fala'])) for c in cenas]
    # SEMPRE casa pelo texto: a voz junta umas palavras ("derrubá-la", números) e separa outras; quando as duas
    # coisas acontecem no mesmo vídeo a contagem bate por acaso e o corte da cena saía uma palavra fora do lugar
    roteiro = [w for c in cenas for w in re.findall(r'\w+', c['fala'])]
    if len(roteiro) != len(palavras):
        print(f'aviso: roteiro com {len(roteiro)} palavras e voz com {len(palavras)}; casando pelo texto')
    palavras = casar_palavras(palavras, roteiro)
    palavras = encurtar_pausas(wav, palavras, cenas, fim_frase=perfil.get('pausa_entre_frases', 0.32))
    palavras = [(w, a + atraso, b + atraso) for w, a, b in palavras]
    por_cena, k = [], 0
    for n in contagem:
        por_cena.append(palavras[k:k + n])
        k += n
    inicios = [0.0] + [pc[0][1] for pc in por_cena[1:]]
    fim = por_cena[-1][-1][2] + 1.0
    duracoes = [b - a for a, b in zip(inicios, inicios[1:] + [fim])]
    total = sum(duracoes)

    # 3. cenas: zoom + legenda de tela alinhada pela fala
    tempos = []                                      # para conferir a sincronia depois (tempos.json)
    for i, c in enumerate(cenas):
        pc = por_cena[i]
        # regra da revisao (21/10): a legenda de baixo mostra a FALA, escrita como se escreve (campo "legenda");
        # "tela" fica para roteiros antigos que nao tem "legenda"
        textos = blocos_tela(c.get('legenda') or c['tela'], 13 if c.get('destaque') else 17)
        blocos = [[t, ini - inicios[i], 0] for t, ini in zip(textos, alinhar_blocos(textos, pc))]
        for j, b in enumerate(blocos):
            b[2] = blocos[j + 1][1] if j + 1 < len(blocos) else duracoes[i]
        json.dump(blocos, open(os.path.join(pasta, f'leg{i}.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        tempos.append({'cena': i, 'inicio': inicios[i], 'palavras': pc,
                       'legenda': [[t, a + inicios[i], b + inicios[i]] for t, a, b in blocos]})
        for j, (t, _, _) in enumerate(blocos):
            legenda_png(t, os.path.join(pasta, f'leg{i}_{j}.png'), perfil, c.get('destaque'))
        canal.cena_video(i, duracoes[i], pasta)

    json.dump(tempos, open(os.path.join(pasta, 'tempos.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    # 4. gancho escrito no topo da 1a cena
    if rot.get('gancho'):
        legenda_png(rot['gancho'], os.path.join(pasta, 'gancho.png'), perfil, destaque=True)
        c0 = os.path.join(pasta, 'cena0.mp4')
        ffmpeg('-i', c0, '-i', os.path.join(pasta, 'gancho.png'), '-filter_complex', '[0:v][1:v]overlay=(W-w)/2:190[v]',
               '-map', '[v]', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', c0 + '.tmp.mp4')
        os.replace(c0 + '.tmp.mp4', c0)
    if som and som.get('rotulo'):
        rot_png = os.path.join(pasta, 'rotulo_som.png')
        Image.new('RGBA', (LARG, 120), (0, 0, 0, 0)).save(rot_png)
        selo_png(rot_png, som['rotulo'], perfil)
        c0 = os.path.join(pasta, 'cena0.mp4')
        ffmpeg('-i', c0, '-i', rot_png, '-filter_complex',
               f"[0:v][1:v]overlay=0:150:enable='lt(t,{som['duracao'] + 0.6:.2f})'[v]",
               '-map', '[v]', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', c0 + '.tmp.mp4')
        os.replace(c0 + '.tmp.mp4', c0)

    # 5. montagem: voz + trilha gerada (sem direito autoral) + granulado fixo (dither contra faixas de cor)
    with open(os.path.join(pasta, 'cenas.txt'), 'w') as f:
        f.writelines(f"file 'cena{i}.mp4'\n" for i in range(len(cenas)))
    drone = ("aevalsrc='0.5*sin(2*PI*55*t)*(0.6+0.4*sin(2*PI*0.13*t))+0.35*sin(2*PI*82.4*t)*(0.6+0.4*sin(2*PI*0.09*t))"
             f"+0.2*sin(2*PI*110.3*t)':s=44100:d={total:.2f}")
    v = perfil['visual']
    final = os.path.join(pasta, 'final.mp4')
    entra_som, mix_som = [], ''
    if som:   # trecho do som real tocando sozinho antes da voz; a trilha so entra depois dele
        entra_som = ['-i', arq_fonte(som['fonte'])]
        mix_som = (f"[4:a]atrim={som['inicio']}:{som['inicio'] + som['duracao']},asetpts=PTS-STARTPTS,"
                   f"aresample=44100,volume={som.get('volume', 2.5)},afade=t=out:st={som['duracao'] - 0.3:.2f}:d=0.3[som];")
    ffmpeg('-f', 'concat', '-safe', '0', '-i', os.path.join(pasta, 'cenas.txt'), '-i', wav,
           '-f', 'lavfi', '-i', drone, '-f', 'lavfi', '-i', f'anoisesrc=c=brown:a=0.4:d={total:.2f}:r=44100', *entra_som,
           '-filter_complex',
           f"[0:v]noise=alls={v.get('granulado', 6)},vignette=PI/5[v];" + mix_som +
           f'[1:a]adelay={int(atraso * 1000)},volume=1.6,acompressor=threshold=0.2:ratio=3[voz];'
           '[3:a]lowpass=f=300[ruido];[2:a][ruido]amix=inputs=2,volume=0.10,'
           f'afade=t=in:st={atraso - ATRASO:.2f}:d=1,afade=t=out:st={total - 1.5:.2f}:d=1.5[trilha];'
           + ('[voz][trilha][som]amix=inputs=3' if som else '[voz][trilha]amix=inputs=2') +
           ':duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5[a]',
           '-map', '[v]', '-map', '[a]', '-t', f'{total:.3f}', '-c:v', 'libx264', '-crf', str(v.get('crf', 22)),
           '-preset', 'slow', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', final)

    # 6. post com creditos gerados das fichas + teste mudo
    usados = [creditos[k] for k in dict.fromkeys([c['imagem'] for c in cenas if c.get('imagem')] +
                                                 [g['fonte'] for g in rot.get('graficos', {}).values() if g.get('fonte')])
              if not rot['fontes'][k].get('audio')]
    json.dump(usados, open(os.path.join(pasta, 'creditos.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    legenda = (rot['post'] + '\n\nFotos e ilustrações de arquivo: ' + imagens.linha_de_creditos(usados) +
               '. Gráficos com dados reais feitos pelo canal.' +
               (f" Som do início: gravação real, {creditos[som['fonte']]['autor']} ({creditos[som['fonte']]['licenca'].lower()})"
                f"{', ' + som['nota'] if som.get('nota') else ''}." if som else '') +
               ' Narração com voz sintética.\n\n' +
               ' '.join('#' + h for h in rot.get('hashtags', [])))
    open(os.path.join(pasta, 'legenda.txt'), 'w', encoding='utf-8').write(legenda)
    tira(final, os.path.join(pasta, 'tira_quadros.png'), total)
    for arq in os.listdir(pasta):
        if re.match(r'(cena\d+\.mp4|leg\d+_\d+\.png|leg\d+\.json|cenas\.txt|gancho\.png|rotulo_som\.png)$', arq):
            os.remove(os.path.join(pasta, arq))

    regras = perfil.get('tiktok', {})
    aviso = '' if regras.get('segundos_min', 0) <= total <= regras.get('segundos_max', 1e9) else '  (FORA da faixa do perfil!)'
    print(f'pronto: {final} ({total:.1f}s, {os.path.getsize(final) / 1e6:.1f} MB){aviso}')
    return final


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    gerar(sys.argv[1], sys.argv[2])
