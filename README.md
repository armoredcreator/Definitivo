# ArmoredCreator

Aplicação local integrada para descobrir vídeos nas três fontes Telegram, validar ofertas Shopee e produzir publicações com processamento pesado sequencial.

**Fluxo:** Sync → Vision → Stock → IA → Speech → Studio → Hub.

As legendas usam um gerador local baseado no contexto aprovado pela Vision e passam pela Policy compartilhada. O fluxo padrão não chama Ollama nem Gemini; quando o título não sustenta uma frase factual segura, usa uma legenda neutra curta para não travar a esteira. Nesses casos, a validação formal não garante a mesma especificidade editorial.

O `START_ALL.bat` é o único ponto de entrada operacional. Sem argumentos, executa o preflight seguro. Para processar a coleta histórica sem teto diário e depois permanecer em LIVE, use `--continuous --publish --continuous-operation-id historico-live --max-items-per-batch 25`, mantendo o mesmo identificador ao retomar. O tamanho do lote define apenas pontos de retomada; não limita o total processado, e o processamento pesado continua serial.

## Instalação

O runtime usa Python 3.11.9 em um único ambiente `.venv`. Tokens, chaves, configurações privadas e sessões Telegram ficam em `credentials/`; esse diretório é local e nunca é enviado ao Git. O Telegram Bot API nativo também fica organizado em `runtime/telegram-bot-api/`.

## Documentação

A arquitetura, instalação, migração do SQLite, parâmetros operacionais, recuperação e evidências estão reunidas em [docs/ARMORED_CREATOR_DOCUMENTO_MESTRE.md](docs/ARMORED_CREATOR_DOCUMENTO_MESTRE.md).
