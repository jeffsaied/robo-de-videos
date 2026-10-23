r"""Canal dark de curiosidades/misterios no YouTube Shorts, 100% automatico.

    python canal.py gerar      -> faz um video em saida\<data-hora>\ (roteiro, imagens, voz, legenda, trilha)
    python canal.py publicar   -> sobe no YouTube o video mais novo que ainda nao subiu
    python canal.py rodar      -> gerar + publicar (e o que o Agendador do Windows chama)
    python canal.py relatorio  -> numeros dos videos no celular (Agendador: segunda 9h)
    python canal.py login      -> abre o navegador uma vez para ligar o canal (gera credenciais\token.json)

Configuracoes em config.json. Avisos (video novo ou erro) vao para o celular pelo mesmo ntfy do Claude.
"""
import json
import os
import random
import re
import subprocess
import sys
import time
import traceback
import urllib.parse
import wave
from datetime import datetime
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

PASTA = os.environ.get('ROBO_DADOS') or os.path.dirname(os.path.abspath(__file__))   # ROBO_DADOS: pasta de dados do app do robo
SAIDA = os.path.join(PASTA, 'saida')
CRED = os.path.join(PASTA, 'credenciais')
HISTORICO = os.path.join(PASTA, 'historico.json')
LARG, ALT, FPS = 1080, 1920, 30


def cfg():
    with open(os.path.join(PASTA, 'config.json'), encoding='utf-8') as f:
        return json.load(f)


def log(msg):
    linha = f'[{datetime.now():%d/%m %H:%M:%S}] {msg}'
    print(linha, flush=True)
    with open(os.path.join(PASTA, 'canal.log'), 'a', encoding='utf-8') as f:
        f.write(linha + '\n')


def celular(titulo, texto, tags='movie_camera'):
    """Mesmo topico do aviso do Claude (Claude-Aviso\\celular.json)."""
    try:
        c = cfg()
        with open(c['aviso_celular'], encoding='utf-8-sig') as f:
            n = json.load(f)
        requests.post(n['servidor'], json={'topic': n['topico'], 'title': titulo, 'message': texto[:300],
                                           'tags': [tags]}, timeout=10)
    except Exception as e:
        log(f'aviso no celular falhou: {e}')


def ler_historico():
    try:
        with open(HISTORICO, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def gravar_historico(h):
    with open(HISTORICO, 'w', encoding='utf-8') as f:
        json.dump(h, f, ensure_ascii=False, indent=1)


# ---------- 1. roteiro (Claude) ----------

PROMPT = """Você escreve roteiros para um canal "dark" de YouTube Shorts em português do Brasil, nicho: {nicho}.

Escreva UM roteiro novo. A marca do canal é: MISTÉRIO REAL + TEORIA INTELIGENTE que tenta explicar ele.
Estrutura obrigatória:
1. Gancho com o mistério real (um caso, sinal, objeto, desaparecimento, paradoxo observado).
2. Os fatos, rápidos.
3. A VIRADA: "Existe uma teoria..." e o NOME da teoria (ex.: Floresta Negra, Paradoxo de Fermi, Grande Filtro, Hipótese da Simulação, Hipótese do Zoológico, Esfera de Dyson, Paradoxo de Bootstrap, Cérebro de Boltzmann). Teorias de ciência, filosofia ou física de verdade, com autor ou origem real quando houver (ex.: "do escritor Liu Cixin", "do físico Enrico Fermi").
4. O que a teoria implica, de um jeito que dê arrepio ("se ela estiver certa, o silêncio do universo é proposital").
5. Uma frase de CTA pedindo inscrição no canal.
6. A resposta final: o que se sabe hoje (explicação mais aceita ou "ainda sem resposta"), fechando o vídeo.
Marque com "destaque": true as cenas em que o NOME da teoria é dito (1 ou 2 cenas). Sempre trate teoria como teoria ("uma hipótese", "alguns cientistas acreditam"), nunca como fato provado.
Regras:
- Só fatos reais, documentados e verificáveis (casos históricos, mistérios sem solução, ciência estranha, lugares, crimes famosos antigos). Se não tiver certeza de um detalhe, não use. Nada de lenda apresentada como fato: se for lenda, diga que é lenda.
- Nada de violência gráfica, nada sobre pessoas vivas não-públicas, nada que viole as regras do YouTube.
- {frases} frases MUITO curtas (6 a 10 palavras cada), total entre 80 e 100 palavras (vídeo de 30 a 40 segundos). Cada frase vira uma imagem, então frases curtas = cortes rápidos.
- A 1ª frase é o gancho: pergunta ou afirmação chocante que prende em 2 segundos. O gancho também tem de ser verdade: não chame de "mensagem" o que é só um sinal, nem fale "de quem"/remetente quando não se sabe se existe um.
- RITMO: os 2 primeiros segundos prendem pela curiosidade; no meio NÃO entregue a resposta, cada frase cria expectativa para a próxima; a resposta (ou a melhor explicação conhecida) vem só no FINAL.
- CTA: logo ANTES da resposta final, uma frase curta pedindo para se inscrever no canal (ex.: "Antes da resposta: se inscreve no canal pra não perder o próximo."). Só essa, uma vez.
- Português falado, simples, tom de suspense. Escreva números por extenso.
- Para cada frase, um prompt de imagem EM INGLÊS para gerar uma ilustração cinematográfica escura e realista daquela cena (sem texto na imagem, sem rostos de pessoas reais, sem sangue). Varie o enquadramento entre as cenas (close, plano aberto, detalhe, vista de cima).
- Uma pergunta curta para o comentário fixado, que divida opiniões e faça a pessoa responder (ex.: "Você acha que foi sinal alienígena ou erro do equipamento?").
{desempenho}
NÃO repita nenhum destes temas já usados: {usados}

Responda SOMENTE com JSON válido, sem comentários, neste formato:
{{"tema": "nome curto do caso", "titulo": "título com no máximo 60 caracteres, curioso, sem clickbait mentiroso", "descricao": "2 a 3 linhas resumindo o caso, terminando com 3 hashtags", "tags": ["8 a 12 tags"], "pergunta": "pergunta para o comentário", "teoria": "nome da teoria", "cenas": [{{"fala": "frase narrada", "imagem": "english image prompt", "destaque": false}}]}}"""


def claude_exe(c):
    """O caminho do claude.exe muda a cada versao da extensao do VS Code: usa o do config e, se sumiu, o mais novo."""
    import glob
    p = c.get('claude_exe', '')
    if p and os.path.exists(p):
        return p
    achados = sorted(glob.glob(os.path.expanduser('~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe')),
                     key=os.path.getmtime)
    if achados:
        return achados[-1]
    import shutil
    return shutil.which('claude') or p


def claude(prompt, c):
    amb = dict(os.environ, CLAUDE_SEM_AVISO='1')   # nao apitar no celular a cada roteiro
    cmd = [claude_exe(c), '-p', '--model', c.get('modelo', 'sonnet'), '--output-format', 'text',
           '--settings', json.dumps({'disableAllHooks': True}),
           '--disallowedTools', 'Bash,PowerShell,Edit,Write,Read,WebFetch,WebSearch,Glob,Grep,Agent,Skill']
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding='utf-8',
                       env=amb, cwd=PASTA, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f'claude falhou ({r.returncode}): {r.stderr[-500:] or r.stdout[-500:]}')
    return r.stdout


def roteiro(c, hist):
    usados = ', '.join(h['tema'] for h in hist[-150:]) or 'nenhum'
    prompt = PROMPT.format(nicho=c['nicho'], frases=c.get('frases', '10 a 13'), usados=usados,
                           desempenho=texto_desempenho())
    for tentativa in range(3):
        bruto = claude(prompt, c)
        try:
            r = json.loads(bruto[bruto.index('{'):bruto.rindex('}') + 1])
            assert 7 <= len(r['cenas']) <= 15 and r['titulo'] and r['tema']
            return r
        except Exception as e:
            log(f'roteiro veio torto ({e}), tentando de novo')
    raise RuntimeError('o Claude não devolveu um roteiro válido 3 vezes')


# ---------- 2. imagens (Pollinations, gratis e sem chave) ----------

ESTILO = ', dark cinematic, moody low-key lighting, film grain, highly detailed, vertical composition, no text'


_ultima_imagem = 0.0


def imagem(prompt, destino, semente):
    """O plano gratis do Pollinations aceita 1 imagem a cada 45 s por IP (402 FREE_LIMIT se passar)."""
    global _ultima_imagem
    url = ('https://image.pollinations.ai/prompt/' + urllib.parse.quote(prompt + ESTILO) +
           f'?width={LARG}&height={ALT}&nologo=true&seed={semente}&model=flux')
    for tentativa in range(4):
        espera = _ultima_imagem + 47 - time.time()
        if espera > 0:
            time.sleep(espera)
        try:
            r = requests.get(url, timeout=120)
            _ultima_imagem = time.time()
            if r.status_code == 402:
                log('Pollinations pediu para esperar (limite gratis)')
                continue
            if r.ok and r.headers.get('content-type', '').startswith('image'):
                img = Image.open(BytesIO(r.content)).convert('RGB')
                w, h = img.size
                img = img.crop((0, 0, w, int(h * 0.94)))          # tira a marca d'agua do rodape
                img = cobrir(img, LARG, ALT)
                img.save(destino, quality=95)
                return
        except Exception as e:
            log(f'imagem falhou ({e})')
        time.sleep(5 + 10 * tentativa)
    log('imagem nao veio: usando fundo escuro')
    fundo = Image.new('RGB', (LARG, ALT), (8, 8, 12))
    fundo.save(destino)


def cobrir(img, w, h):
    esc = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * esc), round(img.height * esc)), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


# ---------- 3. voz (Microsoft neural; Piper offline de reserva) ----------

def narrar(cenas, pasta, c):
    if c.get('motor_voz', 'edge') == 'edge':
        try:
            return narrar_edge(cenas, pasta, c)
        except Exception as e:
            log(f'voz da Microsoft falhou ({e}): usando a Piper')
    return narrar_piper(cenas, pasta, c)


def narrar_edge(cenas, pasta, c):
    import asyncio
    import edge_tts
    duracoes = []
    for i, cena in enumerate(cenas):
        mp3, arq = os.path.join(pasta, f'fala{i}.mp3'), os.path.join(pasta, f'fala{i}.wav')
        fala = edge_tts.Communicate(cena['fala'], c.get('voz_edge', 'pt-BR-AntonioNeural'),
                                    rate=c.get('ritmo_edge', '-5%'), pitch=c.get('tom_edge', '-6Hz'))
        asyncio.run(fala.save(mp3))
        ffmpeg('-i', mp3, '-ar', '44100', '-ac', '1', arq)
        os.remove(mp3)
        with wave.open(arq) as w:
            duracoes.append(w.getnframes() / w.getframerate() + 0.25)
    return duracoes


def narrar_piper(cenas, pasta, c):
    from piper import PiperVoice, SynthesisConfig
    voz = PiperVoice.load(os.path.join(PASTA, 'voz', c.get('voz', 'pt_BR-faber-medium.onnx')))
    conf = SynthesisConfig(length_scale=c.get('ritmo_voz', 0.92))
    duracoes = []
    for i, cena in enumerate(cenas):
        arq = os.path.join(pasta, f'fala{i}.wav')
        with wave.open(arq, 'wb') as w:
            voz.synthesize_wav(cena['fala'], w, syn_config=conf)
        with wave.open(arq) as w:
            duracoes.append(w.getnframes() / w.getframerate() + 0.25)   # respiro entre frases
    return duracoes


# ---------- 4. legenda (PNG por pedaco de frase) ----------

def legenda_png(texto, destino, destaque=False):
    """Cena de destaque (nome da teoria): letra maior e vermelha."""
    fonte = ImageFont.truetype(r'C:\Windows\Fonts\impact.ttf', 122 if destaque else 96)
    img = Image.new('RGBA', (LARG, 420), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    linhas, atual = [], ''
    for p in texto.upper().split():
        teste = (atual + ' ' + p).strip()
        if d.textlength(teste, font=fonte) > LARG - 140 and atual:
            linhas.append(atual)
            atual = p
        else:
            atual = teste
    linhas.append(atual)
    passo = 135 if destaque else 110
    y = (420 - len(linhas) * passo) // 2
    for i, linha in enumerate(linhas):
        cor = (235, 30, 30) if destaque else (255, 214, 0) if i == 0 else (255, 255, 255)
        x = (LARG - d.textlength(linha, font=fonte)) // 2
        d.text((x, y), linha, font=fonte, fill=cor, stroke_width=8, stroke_fill=(0, 0, 0))
        y += passo
    sombra = img.split()[3].filter(ImageFilter.GaussianBlur(14)).point(lambda a: a * 0.6)
    fundo = Image.new('RGBA', img.size, (0, 0, 0, 0))
    fundo.putalpha(sombra)
    Image.alpha_composite(fundo, img).save(destino)


def pedacos(fala, dur):
    """Divide a frase em blocos de ate 3 palavras, com tempo proporcional ao tamanho."""
    palavras = fala.split()
    blocos = [' '.join(palavras[i:i + 3]) for i in range(0, len(palavras), 3)]
    total = sum(len(b) for b in blocos)
    util = dur - 0.25
    t, out = 0.0, []
    for b in blocos:
        d = util * len(b) / total
        out.append((b, t, t + d))
        t += d
    return out


# ---------- 5. montagem (ffmpeg) ----------

def ffmpeg(*args):
    r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError('ffmpeg: ' + r.stderr[-800:])


def cena_video(i, dur, pasta):
    quadros = round(dur * FPS)
    zoom_entra = i % 2 == 0
    z = f"'min(1+0.12*on/{quadros},1.12)'" if zoom_entra else f"'max(1.12-0.12*on/{quadros},1)'"
    filtros = [f"[0:v]scale={2 * LARG}:{2 * ALT},zoompan=z={z}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
               f":d={quadros}:s={LARG}x{ALT}:fps={FPS},eq=brightness=-0.04:saturation=0.85[b]"]
    entradas = ['-i', os.path.join(pasta, f'img{i}.jpg')]
    ultimo = 'b'
    blocos = json.load(open(os.path.join(pasta, f'leg{i}.json'), encoding='utf-8'))
    for k, (_, ini, fim) in enumerate(blocos):
        entradas += ['-i', os.path.join(pasta, f'leg{i}_{k}.png')]
        filtros.append(f"[{ultimo}][{k + 1}:v]overlay=(W-w)/2:{ALT - 760 if ALT > LARG else ALT - 430}:enable='gte(t,{ini:.3f})*lt(t,{fim:.3f})'[v{k}]")
        ultimo = f'v{k}'
    ffmpeg(*entradas, '-filter_complex', ';'.join(filtros), '-map', f'[{ultimo}]', '-t', f'{dur:.3f}',
           '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', str(FPS),
           os.path.join(pasta, f'cena{i}.mp4'))


def montar(pasta, n, duracoes):
    with open(os.path.join(pasta, 'cenas.txt'), 'w') as f:
        f.writelines(f"file 'cena{i}.mp4'\n" for i in range(n))
    # fala com respiro
    with open(os.path.join(pasta, 'falas.txt'), 'w') as f:
        f.writelines(f"file 'fala{i}p.wav'\n" for i in range(n))
    for i in range(n):
        ffmpeg('-i', os.path.join(pasta, f'fala{i}.wav'), '-af', 'apad=pad_dur=0.25', '-ar', '44100', '-ac', '1',
               os.path.join(pasta, f'fala{i}p.wav'))
    total = sum(duracoes)
    # trilha sombria gerada aqui mesmo (sem direito autoral): drone grave + ruido filtrado
    drone = ("aevalsrc='0.5*sin(2*PI*55*t)*(0.6+0.4*sin(2*PI*0.13*t))+0.35*sin(2*PI*82.4*t)*(0.6+0.4*sin(2*PI*0.09*t))"
             f"+0.2*sin(2*PI*110.3*t)':s=44100:d={total:.2f}")
    ffmpeg('-f', 'concat', '-safe', '0', '-i', os.path.join(pasta, 'cenas.txt'),
           '-f', 'concat', '-safe', '0', '-i', os.path.join(pasta, 'falas.txt'),
           '-f', 'lavfi', '-i', drone,
           '-f', 'lavfi', '-i', f'anoisesrc=c=brown:a=0.4:d={total:.2f}:r=44100',
           '-filter_complex',
           '[1:a]volume=1.6,acompressor=threshold=0.2:ratio=3[voz];'
           '[3:a]lowpass=f=300[ruido];[2:a][ruido]amix=inputs=2,volume=0.10,'
           f'afade=t=in:d=1,afade=t=out:st={total - 1.5:.2f}:d=1.5[trilha];'
           '[voz][trilha]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5[a]',
           '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest',
           '-movflags', '+faststart', os.path.join(pasta, 'video.mp4'))


def produzir(cenas, pasta, c):
    """Imagens + voz + legendas + montagem de uma lista de cenas em pasta\\video.mp4. Devolve as duracoes."""
    semente = random.randint(1, 10 ** 6)
    for i, cena in enumerate(cenas):
        if not os.path.exists(os.path.join(pasta, f'img{i}.jpg')):   # recomeco sem baixar de novo
            imagem(cena['imagem'], os.path.join(pasta, f'img{i}.jpg'), semente + i)
    duracoes = narrar(cenas, pasta, c)
    for i, cena in enumerate(cenas):
        blocos = pedacos(cena['fala'], duracoes[i])
        json.dump(blocos, open(os.path.join(pasta, f'leg{i}.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        for k, (txt, _, _) in enumerate(blocos):
            legenda_png(txt, os.path.join(pasta, f'leg{i}_{k}.png'), bool(cena.get('destaque')))
        cena_video(i, duracoes[i], pasta)
    montar(pasta, len(cenas), duracoes)
    for arq in os.listdir(pasta):   # deixa so o que interessa
        if re.match(r'(cena\d+\.mp4|fala\d+p?\.wav|leg\d+_\d+\.png|leg\d+\.json|cenas\.txt|falas\.txt)$', arq):
            os.remove(os.path.join(pasta, arq))
    return duracoes


def gerar():
    c = cfg()
    hist = ler_historico()
    pasta = os.path.join(SAIDA, datetime.now().strftime('%Y-%m-%d_%H%M'))
    os.makedirs(pasta, exist_ok=True)
    log(f'gerando em {pasta}')
    r = roteiro(c, hist)
    json.dump(r, open(os.path.join(pasta, 'roteiro.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    log(f'tema: {r["tema"]} | {r["titulo"]}')
    duracoes = produzir(r['cenas'], pasta, c)
    hist.append({'tema': r['tema'], 'titulo': r['titulo'], 'pasta': pasta, 'data': datetime.now().isoformat(timespec='minutes')})
    gravar_historico(hist)
    log(f'video pronto: {sum(duracoes):.1f}s')
    return pasta


# ---------- 6. YouTube ----------

ENVIAR = 'https://www.googleapis.com/auth/youtube.upload'
COMENTAR = 'https://www.googleapis.com/auth/youtube.force-ssl'
NUMEROS = 'https://www.googleapis.com/auth/yt-analytics.readonly'
ESCOPOS = [ENVIAR, COMENTAR, NUMEROS]
DESEMPENHO = os.path.join(PASTA, 'desempenho.json')


def credencial(interativo=False, precisa=ENVIAR):
    """O token antigo so tem o escopo de enviar; comentar e ler numeros pedem o login de novo."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    token = os.path.join(CRED, 'token.json')
    cred = None
    if os.path.exists(token) and not interativo:
        cred = Credentials.from_authorized_user_file(token)
        if precisa not in (cred.scopes or []):
            raise PermissionError(f'o login do canal nao tem a permissao {precisa.rsplit("/", 1)[1]}: rode "canal.py login"')
        if cred.expired and cred.refresh_token:
            cred.refresh(Request())
    if not cred or not cred.valid:
        if not interativo:
            raise RuntimeError('canal nao ligado: rode "python canal.py login"')
        segredo = os.path.join(CRED, 'client_secret.json')
        if not os.path.exists(segredo):
            raise RuntimeError(f'falta {segredo} (baixe do Google Cloud)')
        cred = InstalledAppFlow.from_client_secrets_file(segredo, ESCOPOS).run_local_server(port=0)
    with open(token, 'w') as f:
        f.write(cred.to_json())
    return cred


def youtube(interativo=False, precisa=ENVIAR):
    from googleapiclient.discovery import build
    return build('youtube', 'v3', credentials=credencial(interativo, precisa))


def comentar(video_id, pergunta):
    """Comentario do proprio canal com a pergunta. A API nao deixa fixar: isso so pelo Studio."""
    try:
        yt = youtube(precisa=COMENTAR)
        yt.commentThreads().insert(part='snippet', body={'snippet': {
            'videoId': video_id, 'topLevelComment': {'snippet': {'textOriginal': pergunta}}}}).execute()
        log(f'comentario postado: {pergunta}')
        return True
    except Exception as e:
        log(f'comentario nao foi: {e}')
        return False


def comentar_pendentes():
    """Comentarios guardados de videos que estavam agendados (privados) e ja foram ao ar."""
    hist = ler_historico()
    agora = datetime.now().astimezone()
    mudou = False
    for h in hist:
        p = h.get('comentar')
        if p and datetime.fromisoformat(p['depois_de']) <= agora and comentar(h['youtube'], p['texto']):
            del h['comentar']
            mudou = True
    if mudou:
        gravar_historico(hist)


# ---------- 7. desempenho (YouTube Analytics) ----------

def atualizar_desempenho():
    from googleapiclient.discovery import build
    an = build('youtubeAnalytics', 'v2', credentials=credencial(precisa=NUMEROS))
    hoje = datetime.now().strftime('%Y-%m-%d')
    r = an.reports().query(ids='channel==MINE', startDate='2026-10-01', endDate=hoje,
                           metrics='views,averageViewPercentage,likes,comments,subscribersGained',
                           dimensions='video', sort='-views', maxResults=200).execute()
    por_id = {linha[0]: linha[1:] for linha in r.get('rows', [])}
    lista = []
    for h in ler_historico():
        if h.get('youtube') in por_id:
            v, ret, lk, cm, ins = por_id[h['youtube']]
            lista.append({'tema': h['tema'], 'titulo': h['titulo'], 'id': h['youtube'], 'views': v,
                          'retencao': round(ret, 1), 'likes': lk, 'comentarios': cm, 'inscritos': ins})
    lista.sort(key=lambda x: -x['views'])
    with open(DESEMPENHO, 'w', encoding='utf-8') as f:
        json.dump({'data': datetime.now().isoformat(timespec='minutes'), 'videos': lista}, f, ensure_ascii=False, indent=1)
    return lista


def texto_desempenho():
    """Trecho do prompt com o que deu certo e errado (so quando ja tem dado suficiente)."""
    try:
        with open(DESEMPENHO, encoding='utf-8') as f:
            vids = json.load(f)['videos']
    except Exception:
        return ''
    if len(vids) < 4:
        return ''
    nota = lambda v: v['views'] * (0.5 + v['retencao'] / 100)
    vids = sorted(vids, key=nota, reverse=True)
    bons = '; '.join(f'{v["tema"]} ({v["views"]} views, {v["retencao"]}% assistido)' for v in vids[:3])
    ruins = '; '.join(f'{v["tema"]} ({v["views"]} views, {v["retencao"]}% assistido)' for v in vids[-3:])
    return (f'- O que mais funcionou no canal até agora: {bons}. Escolha um tema do MESMO TIPO (sem repetir o caso).\n'
            f'- O que funcionou pior: {ruins}. Evite temas parecidos com esses.\n')


def relatorio():
    vids = atualizar_desempenho()
    if not vids:
        celular('Relatorio do canal', 'Ainda sem numeros (o YouTube leva uns 2 dias para mostrar).', 'bar_chart')
        return
    total = sum(v['views'] for v in vids)
    ins = sum(v['inscritos'] for v in vids)
    top = '\n'.join(f'{i + 1}. {v["titulo"][:40]} - {v["views"]} views, {v["retencao"]}%' for i, v in enumerate(vids[:3]))
    celular('Relatorio semanal - Arquivo Dark', f'{len(vids)} videos, {total} views, +{ins} inscritos\n{top}', 'bar_chart')
    log(f'relatorio: {len(vids)} videos, {total} views')


def publicar():
    from googleapiclient.http import MediaFileUpload
    hist = ler_historico()
    pendente = next((h for h in reversed(hist) if not h.get('youtube') and
                     os.path.exists(os.path.join(h['pasta'], 'video.mp4'))), None)
    if not pendente:
        log('nada para publicar')
        return
    c = cfg()
    r = json.load(open(os.path.join(pendente['pasta'], 'roteiro.json'), encoding='utf-8'))
    titulo = r['titulo'][:90] + ' #shorts'
    corpo = {
        'snippet': {'title': titulo, 'description': r['descricao'] + '\n\n#shorts #curiosidades #misterio',
                    'tags': r.get('tags', [])[:15], 'categoryId': '27', 'defaultLanguage': 'pt-BR',
                    'defaultAudioLanguage': 'pt-BR'},
        'status': {'privacyStatus': c.get('privacidade', 'public'), 'selfDeclaredMadeForKids': False,
                   'containsSyntheticMedia': True},
    }
    yt = youtube()
    media = MediaFileUpload(os.path.join(pendente['pasta'], 'video.mp4'), mimetype='video/mp4', resumable=True)
    req = yt.videos().insert(part='snippet,status', body=corpo, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    pendente['youtube'] = resp['id']
    gravar_historico(hist)
    link = f'https://youtube.com/shorts/{resp["id"]}'
    log(f'publicado: {link}')
    if r.get('pergunta'):
        comentar(resp['id'], r['pergunta'])
    celular('Video novo no canal', f'{r["titulo"]}\n{link}')


def main():
    acao = sys.argv[1] if len(sys.argv) > 1 else 'rodar'
    try:
        if acao == 'login':
            youtube(interativo=True)
            print('canal ligado.')
        elif acao == 'gerar':
            gerar()
        elif acao == 'publicar':
            publicar()
        elif acao == 'relatorio':
            relatorio()
        elif acao == 'rodar':
            try:
                atualizar_desempenho()   # o roteiro novo aprende com os numeros
            except Exception as e:
                log(f'sem numeros do canal agora: {e}')
            try:
                comentar_pendentes()
            except Exception as e:
                log(f'comentarios pendentes falharam: {e}')
            pasta = gerar()
            if os.path.exists(os.path.join(CRED, 'token.json')):
                publicar()
            else:
                celular('Video pronto (nao publicado)', f'Canal ainda nao ligado ao YouTube. Video em {pasta}')
        else:
            print(__doc__)
    except Exception as e:
        log('ERRO: ' + traceback.format_exc())
        celular('Canal dark deu erro', f'{acao}: {e}', 'warning')
        sys.exit(1)


if __name__ == '__main__':
    main()
