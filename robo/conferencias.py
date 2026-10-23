r"""Conferencias automaticas do video pronto (sem IA de texto): pronuncia e volume.

pronuncia(pasta, rot) -> lista de nomes que a voz nao falou de um jeito reconhecivel
    Transcreve narracao.wav com faster-whisper (modelo "small", CPU) e procura cada nome proprio do roteiro
    (palavra com maiuscula fora do inicio de frase, siglas e nomes com numero) na transcricao. Compara pela
    escrita da legenda E pela fala (que pode ter grafia fonetica, ex.: "Umuamua"). Quem nao aparecer, nem
    parecido (>= 0,75), volta como suspeito. O Whisper tambem erra nomes raros: e um aviso, nao um veto.

volume(final) -> LUFS integrado do video (ffmpeg loudnorm); o alvo das plataformas e -14.
"""
import json
import re
import subprocess
import unicodedata
import wave
from difflib import SequenceMatcher

import numpy as np

_modelo = None


def _norm(w):
    w = unicodedata.normalize('NFD', w.lower())
    return ''.join(ch for ch in w if ch.isalnum())


def _nomes(texto):
    """Nomes proprios: maiuscula que nao abre frase, siglas (NOAA) e termos com digito (3I/ATLAS)."""
    nomes = []
    for frase in re.split(r'(?<=[.!?:])\s+', texto):
        palavras = re.findall(r"[\wÀ-ÿ'/-]+", frase)
        for i, p in enumerate(palavras):
            limpa = p.strip("'-/")
            if len(limpa) < 3:
                continue
            sigla = limpa.isupper() and len(limpa) >= 3
            maiuscula = limpa[0].isupper() and i > 0
            if sigla or maiuscula or (re.search(r'\d', limpa) and re.search(r'[A-Za-z]', limpa)):
                nomes.append(limpa)
    return nomes


def _transcrever(wav):
    global _modelo
    from faster_whisper import WhisperModel
    if _modelo is None:
        _modelo = WhisperModel('small', device='cpu', compute_type='int8')
    with wave.open(wav) as w:                        # entrega o audio pronto: o "av" instalado quebra no decode
        taxa = w.getframerate()
        som = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float32) / 32768
        if w.getnchannels() > 1:
            som = som.reshape(-1, w.getnchannels()).mean(axis=1)
    if taxa != 16000:
        som = np.interp(np.arange(0, len(som), taxa / 16000), np.arange(len(som)), som).astype(np.float32)
    segs, _ = _modelo.transcribe(som, language='pt')
    return ' '.join(s.text for s in segs)


def _aparece(nome, palavras_ouvidas):
    n = _norm(nome)
    if not n:
        return True
    tam = max(1, round(len(n) / 6))                  # nome comprido pode virar 2 palavras na transcricao
    for i in range(len(palavras_ouvidas)):
        for k in range(1, tam + 2):
            junto = ''.join(palavras_ouvidas[i:i + k])
            if junto and SequenceMatcher(None, n, junto).ratio() >= 0.75:
                return True
    return False


def pronuncia(pasta, rot):
    import os
    wav = os.path.join(pasta, 'narracao.wav')
    if not os.path.exists(wav):
        return {'feito': False, 'motivo': 'sem narracao.wav', 'suspeitos': []}
    ouvido = _transcrever(wav)
    palavras_ouvidas = [_norm(w) for w in re.findall(r'[\wÀ-ÿ]+', ouvido)]
    suspeitos = []
    for i, c in enumerate(rot['cenas']):
        escrita = _nomes(c.get('legenda') or c.get('tela', ''))
        falada = _nomes(c['fala'])
        for nome in dict.fromkeys(escrita):
            alternativas = [nome] + [f for f in falada if SequenceMatcher(None, _norm(f), _norm(nome)).ratio() >= 0.5]
            if not any(_aparece(a, palavras_ouvidas) for a in alternativas):
                suspeitos.append({'cena': i, 'nome': nome})
    return {'feito': True, 'suspeitos': suspeitos, 'transcricao': ouvido}


def volume(final):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', final, '-af', 'loudnorm=print_format=json',
                        '-f', 'null', '-'], capture_output=True, text=True)
    m = re.search(r'\{[^{}]*"input_i"[^{}]*\}', r.stderr, re.S)
    return float(json.loads(m.group(0))['input_i']) if m else None


# ---------- imagens repetidas entre videos (hash perceptual) ----------
def _dhash(arq, lado=8):
    """Diferenca de brilho entre vizinhos numa miniatura 9x8: muda pouco com recorte leve, tamanho ou compressao."""
    from PIL import Image
    im = Image.open(arq).convert('L').resize((lado + 1, lado), Image.LANCZOS)
    px = list(im.getdata())
    bits = 0
    for y in range(lado):
        for x in range(lado):
            bits = (bits << 1) | (px[y * (lado + 1) + x] > px[y * (lado + 1) + x + 1])
    return bits


def repetidas(pasta, pasta_canal, ultimos=10, limite=6):
    """Compara as imagens de fontes deste video com as dos ultimos `ultimos` videos do canal (registro em
    imagens_usadas.json) e registra as deste. Volta [(arquivo, video_anterior)] das que ja apareceram."""
    import glob
    import os
    reg_arq = os.path.join(pasta_canal, 'imagens_usadas.json')
    try:
        reg = json.load(open(reg_arq, encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        reg = []
    video = os.path.basename(os.path.normpath(pasta))
    meus = {}
    for arq in sorted(glob.glob(os.path.join(pasta, 'fontes', '*'))):
        if arq.endswith('.json') or arq.endswith('.ogg'):
            continue
        try:
            meus[os.path.basename(arq)] = _dhash(arq)
        except Exception:
            continue
    anteriores = [r for r in reg if r['video'] != video][-ultimos:]
    achadas = []
    for nome, h in meus.items():
        for r in anteriores:
            if any(bin(h ^ int(x, 16)).count('1') <= limite for x in r['hashes']):
                achadas.append((nome, r['video']))
                break
    reg = [r for r in reg if r['video'] != video] + [{'video': video, 'hashes': [format(h, '016x') for h in meus.values()]}]
    json.dump(reg[-50:], open(reg_arq, 'w', encoding='utf-8'), indent=1)
    return achadas


# ---------- texto dentro das imagens (OCR com Tesseract) ----------
TESSERACT = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
NOSSOS = {'ilustracao', 'foto', 'real', 'reconstrucao', 'replica', 'moderna', 'tomografia', 'raio', 'epicentro',
          'hidrofone', 'noaa', 'outro', 'bolido', 'som', 'acelerado', 'oumuamua', 'cisne', 'de', 'da', 'do'}


def texto_nas_imagens(pasta, rot, confianca=88):
    """Le as imagens das cenas de foto (img<N>.jpg, ja recortadas como no video) e devolve [(cena, texto)] quando
    sobra texto que nao e nosso (selo, marcador): rotulo em ingles, letreiro cortado, marca d'agua. Grafico proprio
    e pulado. Sem Tesseract instalado, volta None."""
    import csv
    import io
    import os
    if not os.path.exists(TESSERACT):
        return None
    achados = []
    for i, c in enumerate(rot['cenas']):
        if c.get('grafico'):
            continue
        img = os.path.join(pasta, f'img{i}.jpg')
        if not os.path.exists(img):
            continue
        r = subprocess.run([TESSERACT, img, 'stdout', '-l', 'eng+por', '--psm', '11', 'tsv'],
                           capture_output=True, text=True, encoding='utf-8', errors='ignore',
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        palavras = []
        for linha in csv.DictReader(io.StringIO(r.stdout), delimiter='\t', quoting=csv.QUOTE_NONE):
            w = (linha.get('text') or '').strip()
            try:
                conf = float(linha.get('conf') or -1)
            except ValueError:
                conf = -1
            limpa = _norm(w)
            if conf >= confianca and len(limpa) >= 4 and limpa.isalpha() and not any(limpa in n for n in NOSSOS):   # pedaco de selo nosso ("RACAO") nao conta
                palavras.append(w)
        if palavras:                                  # rotulo real passa de 90 de confianca; textura e manuscrito ficam abaixo de 82
            achados.append((i, ' '.join(palavras[:8])))
    return achados
