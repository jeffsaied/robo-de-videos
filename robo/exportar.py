r"""Copia so o que o app do robo precisa para o repo publico (C:\robo-de-videos) e gera o RoboDeVideos.exe.
Nada de segredo, historico ou config pessoal vai junto.

    .\.venv\Scripts\python.exe robo\exportar.py
"""
import json
import os
import re
import shutil
import subprocess
import sys

ORIGEM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = r'C:\robo-de-videos'
ARQUIVOS = ['app_robo.py', 'canal.py', 'fabrica_tiktok.py', 'graficos.py', '.env.example',
            'motores/__init__.py', 'motores/imagens.py', 'motores/voz.py',
            'robo/__init__.py', 'robo/__main__.py', 'robo/banco.py', 'robo/ciclo.py', 'robo/ia.py', 'robo/pesquisa.py', 'robo/conferencias.py',
            'robo/exportar.py', 'robo/LEIA.md']
CANAIS = ['casos-curiosos']
PESSOAIS = ('claude_exe', 'aviso_celular', 'telegram_config', 'telegram_nome', 'telegram_canal')


def copia(rel, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(os.path.join(ORIGEM, rel), dest)


def main():
    for rel in ARQUIVOS:
        copia(rel, os.path.join(DESTINO, rel))
    # semente: o que o .exe copia para Documentos\Robo de Videos na 1a vez
    sem = os.path.join(DESTINO, 'semente')
    shutil.rmtree(sem, ignore_errors=True)
    conf = json.load(open(os.path.join(ORIGEM, 'config.json'), encoding='utf-8'))
    conf = {k: v for k, v in conf.items() if k not in PESSOAIS}
    os.makedirs(os.path.join(sem, 'robo'))
    json.dump(conf, open(os.path.join(sem, 'config.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    robo = json.load(open(os.path.join(ORIGEM, 'robo', 'robo.json'), encoding='utf-8'))
    robo['canal_padrao'] = CANAIS[0]
    json.dump(robo, open(os.path.join(sem, 'robo', 'robo.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    copia('.env.example', os.path.join(sem, '.env.example'))
    for cn in CANAIS:
        copia(f'canais/{cn}/canal.json', os.path.join(sem, 'canais', cn, 'canal.json'))
    versao = re.search(r"VERSAO = '([\d.]+)'", open(os.path.join(ORIGEM, 'app_robo.py'), encoding='utf-8').read())[1]
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed', '--name', 'RoboDeVideos',
                    '--add-data', 'semente;semente', '--hidden-import', 'canal', '--hidden-import', 'edge_tts',
                    '--exclude-module', 'google', '--exclude-module', 'googleapiclient', '--exclude-module', 'piper',
                    '--exclude-module', 'faster_whisper', '--exclude-module', 'ctranslate2', '--exclude-module', 'onnxruntime',
                    '--exclude-module', 'torch', 'app_robo.py'], cwd=DESTINO, check=True)
    print(f'pronto: {DESTINO}\\dist\\RoboDeVideos.exe (versao {versao})')


if __name__ == '__main__':
    main()
