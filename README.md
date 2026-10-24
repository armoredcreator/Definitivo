# ArmoredCreator

Aplicação local integrada para descobrir vídeos nas três fontes Telegram, validar ofertas Shopee e produzir publicações com processamento pesado sequencial.

**Fluxo:** Sync → Vision → Stock → IA → Speech → Studio → Hub.

O `START_ALL.bat` é o único ponto de entrada operacional. Sem argumentos, executa o preflight seguro; a operação exige os argumentos e os limites descritos no documento mestre.

## Instalação

O runtime usa Python 3.11.9 e um único `.venv` na raiz. Tokens, chaves, configurações privadas e sessões Telegram ficam em `credentials/`; esse diretório é local e nunca é enviado ao Git. O Telegram Bot API nativo fica organizado na pasta local `runtime/telegram-bot-api/`.

## Documentação

A arquitetura, instalação, migração do SQLite, parâmetros operacionais, recuperação e evidências estão reunidas em [docs/ARMORED_CREATOR_DOCUMENTO_MESTRE.md](docs/ARMORED_CREATOR_DOCUMENTO_MESTRE.md).
