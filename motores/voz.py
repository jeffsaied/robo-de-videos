r"""Motor de voz: narrar(texto, perfil, pasta) -> (wav, palavras).

`palavras` = [(palavra, inicio_s, fim_s), ...] na ordem da fala. Qual motor usar vem de perfil['motores']['voz'];
as opcoes de cada um ficam em perfil['voz'][<motor>]. Trocar de voz e mudar uma palavra no canal.json.
"""
import asyncio
import base64
import json
import os
import re
import subprocess

import requests


def narrar(texto, perfil, pasta):
    motor = perfil['motores']['voz']
    if motor not in MOTORES:
        raise ValueError(f'motor de voz desconhecido: {motor} (tem: {", ".join(MOTORES)})')
    mp3, palavras = MOTORES[motor](texto, perfil['voz'].get(motor, {}), perfil, pasta)
    wav = os.path.join(pasta, 'narracao.wav')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', mp3, '-ar', '44100', '-ac', '1', wav], check=True)
    os.remove(mp3)
    return wav, palavras


def _edge(texto, op, perfil, pasta):
    import edge_tts
    fala = edge_tts.Communicate(texto, op.get('voz', 'pt-BR-AntonioNeural'), rate=op.get('ritmo', '+0%'),
                                pitch=op.get('tom', '+0Hz'), boundary='WordBoundary')
    audio, palavras = bytearray(), []

    async def puxar():
        async for p in fala.stream():
            if p['type'] == 'audio':
                audio.extend(p['data'])
            elif p['type'] == 'WordBoundary':
                ini = p['offset'] / 1e7
                palavras.append((p['text'], ini, ini + p['duration'] / 1e7))
    asyncio.run(puxar())
    mp3 = os.path.join(pasta, 'narracao.mp3')
    with open(mp3, 'wb') as f:
        f.write(audio)
    return mp3, palavras


def _elevenlabs(texto, op, perfil, pasta):
    """Endpoint with-timestamps: devolve o audio e o tempo de cada letra; aqui as letras viram palavras.
    A chave fica no arquivo apontado por op['chave_arquivo'] (relativo a pasta do canal). Plano gratis NAO
    permite uso comercial."""
    chave = open(os.path.join(perfil['_pasta'], op['chave_arquivo']), encoding='utf-8').read().strip()
    r = requests.post(f'https://api.elevenlabs.io/v1/text-to-speech/{op["voz_id"]}/with-timestamps',
                      headers={'xi-api-key': chave},
                      json={'text': texto, 'model_id': op.get('modelo', 'eleven_multilingual_v2')}, timeout=300)
    r.raise_for_status()
    d = r.json()
    mp3 = os.path.join(pasta, 'narracao.mp3')
    with open(mp3, 'wb') as f:
        f.write(base64.b64decode(d['audio_base64']))
    al = d['alignment']
    palavras, atual, ini = [], '', None
    for ch, a, b in zip(al['characters'], al['character_start_times_seconds'], al['character_end_times_seconds']):
        if re.match(r'\w', ch):
            if not atual:
                ini = a
            atual, fim = atual + ch, b
        elif atual:
            palavras.append((atual, ini, fim))
            atual = ''
    if atual:
        palavras.append((atual, ini, fim))
    return mp3, palavras


MOTORES = {'edge': _edge, 'elevenlabs': _elevenlabs}
