# Robô de Vídeos

Produz vídeos curtos verticais (1080×1920) para qualquer canal e entrega na **fila** com legenda e hashtags. **Quem posta é você**: ele não publica nada sozinho.

## Instalar

1. Baixe o `RoboDeVideos.exe` na última versão em [Releases](../../releases/latest).
2. Instale o ffmpeg (uma vez): `winget install Gyan.FFmpeg`.
3. Para escrever o roteiro ele usa o Claude Code (`claude`) instalado no PC, ou uma chave da API em `Documentos\Robo de Videos\.env` (`ANTHROPIC_API_KEY`, com `"provedor": "anthropic_api"` no `robo\robo.json`).

## Usar

- **Produzir vídeo agora**: pesquisa o tema, escreve e confere o roteiro e monta o vídeo (cerca de 6 minutos).
- **Abrir fila**: cada pasta tem `video.mp4`, `tiktok_legenda.txt`, `hashtags.txt`, `youtube.txt` e `fontes.txt`.
- **Agendar todo dia**: cria a tarefa no Agendador do Windows na hora escolhida.
- **Atualizar**: baixa a versão mais nova daqui do GitHub e reabre o app.

Os dados ficam em `Documentos\Robo de Videos` e continuam lá quando o app é atualizado. Para criar um canal novo, copie `canais\casos-curiosos\canal.json` para uma pasta nova.

Detalhes do funcionamento: [robo/LEIA.md](robo/LEIA.md).
