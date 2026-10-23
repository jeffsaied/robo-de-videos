# Robô de vídeos

Produz vídeos **sem limite por dia** (quantos pedir; agendado, 1 por dia) para qualquer canal (perfil em `canais\<canal>\canal.json`) e deixa na **fila** para uma pessoa conferir e postar. Ele **não publica nada sozinho**.

## Como funciona

| Etapa | O que faz | IA? |
|---|---|---|
| 1. Pesquisar | Wikipedia (categorias do perfil do canal) → escolhe um tema ainda não usado, com texto suficiente e pelo menos 4 imagens de licença livre no Commons | Não |
| 2. Roteiro | Escreve o roteiro só com o texto da fonte, na estrutura do canal (curiosidade → meio sem entregar → CTA → resposta) | Sim (1 chamada) |
| 3. Fatos | Confere o roteiro contra a fonte; se achar problema, reescreve uma vez | Sim (1–2 chamadas) |
| 4. Montar | `fabrica_tiktok.py`: imagens do Commons com licença conferida, voz edge-tts, legenda sincronizada, 1080×1920 | Não |
| 5. Conferir | Duração, resolução, áudio, tamanho, créditos, licença NC, palavras a vigiar, **volume (-14 LUFS)**, **pronúncia (faster-whisper)** e **imagem repetida dos últimos 10 vídeos** (`robo\conferencias.py`) | Não |
| 6. Fila | `robo\fila\<data>_<canal>_<tema>\`: vídeo, legenda do TikTok, hashtags, título/descrição/tags do YouTube, fontes e licenças | Não |

Cada etapa fica gravada em `robo\robo.db` (SQLite). Se o ciclo cair, o próximo **retoma da etapa que faltou**. Dois ciclos ao mesmo tempo são bloqueados (`robo\robo.lock`). Um tema usado nunca volta.

## Regras que já vêm no robô (pedidas pelo dono)

- Estrutura: curiosidade nos 2 primeiros segundos → meio sem entregar a resposta → CTA "Se inscreve no canal, que a resposta vem agora." → resposta no final (vem do `canal.json`: `estrutura_roteiro`, `cta_padrao`).
- Legenda de baixo = a fala, palavra por palavra, com números escritos como se escrevem; nenhum bloco termina em "não/nem/nunca/sem".
- Voz corrida: pontuação real, pausa de no máximo 0,32 s no fim da frase e 0,16 s dentro dela (0,7 s só em cena de suspense).
- Corte das cenas casado pela escrita de cada palavra: a última palavra de uma frase não vaza para a cena seguinte.
- Só imagem com licença livre (nada NC), com crédito no post; ilustração leva o selo ILUSTRAÇÃO, **inclusive sozinho**: `motores\imagens.py` lê o título e a descrição do Commons (artist's impression, illustration, concept, rendering, representation...).
- Conferência de fatos confere um por um ano, década, número e nome contra a fonte.
- Ao postar no TikTok, escolher cada hashtag na lista que aparece ao digitar (fica num tom mais escuro).
- Trava de conta: `tarefas\conta_tiktok.js` confere a conta logada no TikTok contra `canal.json` → `tiktok.conta` (canal em `CANAL`, padrão arquivo-dark). `legenda_tiktok.js` e `hashtags_tiktok.js` chamam a trava antes de mexer no post; se a conta for outra, ou se o TikTok estiver deslogado, param sem fazer nada. Teste: `node tarefas\conta_tiktok.js <canal>`.

## Comandos (PowerShell, na pasta `C:\canal-dark`)

```powershell
.\.venv\Scripts\python.exe -m robo produzir --canal casos-curiosos          # um vídeo agora
.\.venv\Scripts\python.exe -m robo produzir --canal casos-curiosos --sem-ia # só pesquisa: para em "precisa_roteiro"
.\.venv\Scripts\python.exe -m robo fila                                       # o que está esperando
.\.venv\Scripts\python.exe -m robo aprovar 3
.\.venv\Scripts\python.exe -m robo postado 3 tiktok https://www.tiktok.com/...
.\.venv\Scripts\python.exe -m robo custos                                     # chamadas de IA e custo estimado
powershell -ExecutionPolicy Bypass -File .\robo\agendar.ps1 -Hora 09:00 -Canal casos-curiosos
```

## IA e custos (`robo\robo.json`)

- `provedor: "claude_cli"` (padrão): usa o `claude.exe` da extensão do VS Code, ou seja, a **assinatura do Claude**. Não há cobrança por chamada, mas há o limite de uso da assinatura. O custo gravado é só a estimativa que o próprio `claude.exe` informa.
- `provedor: "anthropic_api"`: API paga. Precisa de `ANTHROPIC_API_KEY` no `.env` e da tabela `preco_por_milhao_usd` preenchida com os **preços oficiais** (hoje está zerada de propósito).
- Limites (0 = sem limite, que é o padrão): `videos_por_dia`, `max_chamadas_dia` e `max_custo_usd_dia` (este só vale para `anthropic_api`). Ao atingir um deles o ciclo **para com segurança** e deixa o dossiê da pesquisa na fila (`..._SEM_ROTEIRO`).
- Mesma pergunta = resposta do cache (não gasta de novo).

## Novo canal

Copie `canais\casos-curiosos\canal.json` para `canais\<novo>\canal.json` e troque `nome`, `nicho`, `regras_roteiro`, `estrutura_roteiro`, `cta_padrao` e `robo.fontes.wikipedia_categorias`.

## App (.exe) e atualizações

O `app_robo.py` vira o `RoboDeVideos.exe` (janela com Produzir / Abrir fila / Agendar / Atualizar), publicado em github.com/jeffsaied/robo-de-videos. Os dados do app ficam em `Documentos\Robo de Videos`; aqui no `C:\canal-dark` nada muda.

Para lançar uma atualização:
1. Subir `VERSAO` no `app_robo.py` (ex.: `1.0.1`).
2. `.\.venv\Scripts\python.exe robo\exportar.py`: copia o código para `C:\robo-de-videos` e gera `dist\RoboDeVideos.exe`.
3. No `C:\robo-de-videos`: `git add -A; git commit -m "..."; git push; gh release create v1.0.1 dist\RoboDeVideos.exe --title v1.0.1`.

O botão **Atualizar** lê a última release do GitHub; se a versão for maior, baixa o .exe, troca pelo atual e reabre.

## Postagem

O robô entrega tudo pronto e a pessoa posta. YouTube: a API oficial já funciona neste PC (`canal.py`), mas o robô não usa — publicar continua manual, por decisão do dono. TikTok: a Content Posting API exige app de desenvolvedor aprovado pela TikTok; sem auditoria ela só publica como privado.
