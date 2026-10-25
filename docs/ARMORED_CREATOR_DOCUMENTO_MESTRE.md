# ArmoredCreator — documento mestre

Este é o documento operacional único do repositório Definitivo. Ele registra arquitetura, instalação, estado histórico, proteções e validação. A instalação anterior em `C:\Users\Administrador\Downloads\ArmoredCreator-final` é mantida como referência; a nova aplicação roda em `C:\Users\Administrador\Downloads\Definitivo`.

## Objetivo e decisões

O sistema integra **Sync → Vision → Stock → IA → Speech → Studio → Hub**. A descoberta e a classificação podem percorrer muitos itens por lotes persistidos no SQLite. A produção de mídia é serial: somente um vídeo pode ocupar Stock/IA/Speech/Studio/Hub por vez.

Sync registra metadados sem baixar mídia. Vision e a deduplicação decidem elegibilidade antes da criação de workspace. O diretório `storage/videos/{content_id}` é criado somente quando um item aprovado é selecionado em Stock. IDs de conteúdo incluem a fonte Telegram e o ID da mensagem para evitar colisões entre canais.

Não são usados Redis, RabbitMQ, Celery ou filas físicas. O SQLite guarda estados, checkpoints, orçamento, deduplicação, histórico de publicação e recuperação.

## Responsabilidades dos módulos

| Módulo | Responsabilidade |
| --- | --- |
| ArmoredSync | Três fontes Telegram, descoberta, relação entre mensagem/vídeo/link, metadados e checkpoints. Não baixa mídia na descoberta. |
| ArmoredVision | Resolver produto/oferta, identidade Shopee, link afiliado, contexto de produto, aprovação e orçamento persistente. Consultas reais só com autorização e quota configuradas. |
| ArmoredStock | Materializar o original de um único item aprovado, criar workspace, validar arquivo e SHA-256. |
| ArmoredIA | Gerar legenda editorial brasileira usando Ollama local como padrão; Gemini é opcional. Normalizar e avaliar sentido, contexto e hashtags; a legenda aprovada contém exatamente um 🧡 no início. |
| ArmoredSpeech | Único dono de extração, classificação de áudio, decisão de rota, RVC Melody, efeitos, volumes e trilha final. `PT_BR_NARRATION → RVC Melody`; música/idioma estrangeiro/sem áudio seguem a política aprovada de silenciar o original e aplicar efeito. |
| ArmoredStudio | Apenas análise/tratamento visual, crop 9:16, montagem MP4 e integração da trilha final do Speech. Não classifica áudio nem executa RVC; FFprobe valida o resultado. |
| ArmoredHub | Publicar somente pelo comando explícito, persistir recibo e reconciliar resultado. Nenhum envio real acontece no preflight. |

O Coordinator integra os módulos e impõe a sequência. Discovery leve pode ocorrer durante produção se não competir pelos recursos pesados. Todo caminho de materialização e processamento em catch-up deve selecionar somente um item; Speech/Studio recebem listas unitárias.

## Estados e retorno para Stock

Vision aprovado é representado pelo item `RECEIVED` com `affiliate_url` persistida. A migração `20261024_001_requeue_approved_to_stock` foi corrigida para nunca alterar `PUBLISHED`, `PUBLISHING` ou itens com recibo de publicação. A migração corretiva `20261024_002_restore_publication_fences` usou os eventos preservados para restaurar 15 itens com recibo `CONFIRMED` ao estado terminal `PUBLISHED`. Sete itens com publicação pendente, enviada sem verificação ou etapa de envio sem recibo voltaram para `RECOVERY`. A migração `20261024_003_fence_missing_legacy_receipts` criou travas duráveis para os três casos `PUBLISHING` sem recibo; a quarentena local contém oito itens ambíguos no total, incluindo recibos pendentes fora do conjunto de 23. Nenhum deles pode voltar automaticamente à produção ou ser reenviado. Um `RECOVERY` sem recibo e sem histórico de envio retornou a `RECEIVED` para aguardar Stock.

A primeira migração havia reencaminhado **23 itens** (15 `PUBLISHED`, 5 `PUBLISHING`, 3 `RECOVERY`) e limpado referências derivadas; o backup original preservou os estados e evidências anteriores. A correção foi aplicada somente na cópia nova em 24/10/2026 e alterou 22 estados: 15 `PUBLISHED`, 7 `RECOVERY`; o item restante, `RECOVERY` sem recibo e sem histórico de envio, continuou em `RECEIVED`. Os 20 recibos e todos os eventos anteriores permanecem preservados; nada foi apagado dos tópicos. As correções são idempotentes, registradas em `migration_audit` e precedidas por backups consistentes do SQLite.

O histórico de publicação não autoriza apagar mensagens de tópicos. O código não executa exclusão de mensagens, não envia Telegram no START/preflight e não faz buscas Shopee sem quota autorizada. Itens em quarentena continuam bloqueados até reconciliação apropriada.

## Banco e preservação

O banco operacional é `storage/database/armoredcreator.db`. Ele foi copiado por SQLite Backup API; quatro bancos auxiliares ativos também foram copiados pelo mesmo mecanismo. A instalação anterior e suas credenciais permanecem intactas.

O backup consistente anterior à migração tem 14.486 itens, 78.074 eventos de estado, 20 publicações, 3 fontes e 48 relações fonte/tópico. A base mantém os mesmos 14.486 itens e 20 recibos; a correção acrescentou 22 eventos auditáveis sem apagar os 23 eventos da primeira migração. Os dois backups consistentes e os relatórios estão em `storage/backups/` e `storage/validation/`, ignorados pelo Git. Não há pasta de auditoria nem relatório solto na raiz.

As reclamações históricas de identidade de produto são semeadas de forma determinística quando a deduplicação é inicializada; a migração de estado não reescreve itens ou identidade. O dono canônico considera publicação confirmada, avanço durável, render e original com hash verificado. Duplicados ficam registrados e apontam para o canônico. A validação não remove histórico nem arquivos.

O banco principal é a fonte de verdade. Os bancos auxiliares mantêm áreas duráveis com responsabilidade específica: `armoredspeech.sqlite3` guarda decisões/resultados do Speech; `catch-up-work-budget.sqlite3` guarda atribuições e limites persistentes de lote; `publication-quarantine.sqlite3` guarda evidência de publicações ambíguas; `republication-ledger.sqlite3` impede republicação. Arquivos `-wal` e `-shm` são sidecars temporários mantidos pelo SQLite; não são bancos ou cópias adicionais. Todos os bancos passam `PRAGMA quick_check=ok` e `foreign_key_check` vazio.

## Layout e dados locais

Código, testes, scripts e o documento mestre são versionáveis. `.env.example` é apenas um modelo sem credenciais e não é carregado pela aplicação; a única fonte de configuração privada e sessões é `credentials/`, ignorado pelo Git. SQLite, checkpoints, logs, backups e vídeos ficam em `storage/`, também ignorado. Os caches de Whisper/AudioSet ficam em `runtime/models/audio/` e os modelos RVC permanecem em runtime local ignorado. Efeitos privados e executável Bot API não são publicados no repositório.

O caminho opcional `ARMORED_LEGACY_MEDIA_ROOT` aponta para `ArmoredCreator-final\storage`. É uma origem local confiável somente para leitura: Stock copia o original selecionado, confere estabilidade e SHA-256, e nunca move nem altera o arquivo antigo. Sem esta configuração, originais fora da raiz nova são recusados.

Para transportar o projeto, instalar o código e provisionar separadamente: `credentials/project.env`, sessões Telegram, bancos SQLite e suas cópias, executável/runtime Telegram Bot API, pesos RVC e demais modelos, efeito de áudio em `ArmoredSpeech/assets/efeitosonoro.wav`, e eventuais originais necessários. O efeito é propriedade do Speech; o Studio não mantém cópia. Não transportar `.venv`; ele é recriado a partir do lock.

## Python e instalação

O runtime suportado é Windows amd64 com Python **3.11.9**, em um único ambiente `.venv` na raiz do projeto. Dependências fixadas estão em `requirements-runtime311.lock.txt`; Fairseq/RVC localizados e revisados ficam em `runtime/packages/rvc311`. Os fontes/hash usados para construir a wheel RVC são registrados em `runtime/packages/sources`.

No PowerShell, a partir da raiz do repositório:

```powershell
.\scripts\bootstrap.ps1
```

O script recusa uma versão Python diferente ou `.venv` já existente; instala o lock e o pacote, e termina com `pip check`. Se já houver ambiente, inspecione-o antes de qualquer ação. FFmpeg, Bot API e modelos de áudio são dependências locais/nativas e não criam outro ambiente Python. Modelos de classificação/Whisper ficam em `runtime/models/audio/` (atualmente cerca de 425 MB locais); o preflight valida a presença sem baixar nem executar inferência.

## Configuração de Telegram e limites externos

Preencha os segredos e IDs em `credentials/project.env`; use `.env.example` apenas como referência sem segredos. Configure as três fontes e as três rotas de destino conforme contrato. `BOT_API_EXE` pode apontar para `runtime/telegram-bot-api/telegram-bot-api.exe` dentro da raiz, usando o executável local validado.

As associações são fixas e também são impostas pelo validador de configuração; não basta que os três destinos sejam distintos:

| Fonte | Chat de destino | Tópico |
| --- | --- | ---: |
| `-1003788989075` | `-1004341972306` | 228 |
| `-1002698134896` | `-1004341972306` | 1160 |
| `-1002039708059` | `-1004341972306` | 1327 |

`START_ALL.bat` sem argumento executa preflight e validação de configuração. `--run` ou `--continuous` inicia o Coordinator; Hub real requer o comando/opção explícita de publicação do CLI. Consultas comerciais também dependem da flag, autorização estável, orçamento, evidência e validade. O programa não deve inferir autorização a partir de credenciais presentes.

## Operação e recovery

O SQLite é a fronteira de retomada. Antes de processar, valide configuração, integridade do banco, fontes, espaço e modelos. Sync/ Vision persistem decisões e checkpoints. Stock baixa um item aprovado por vez; original é imutável e validado por hash. Artefatos incompletos são preservados com recibo para inspeção. IA, Speech e Studio salvam progresso com identidade do item. Hub registra tentativa e recibo; resultado incerto permanece em `RECOVERY`/quarentena até reconciliação e nunca é tratado como ausência confirmada.

Não apague `.part`, arquivos de resultado, recibos, quarentenas ou checkpoints manualmente. Refaça preflight e use os comandos de recuperação descritos pelo CLI. Backups de SQLite devem usar a API de backup, especialmente com WAL ativo. Mantenha a cópia anterior até confirmar o funcionamento da nova versão.

## Recursos do notebook

O limite de produção é estrito: um vídeo por vez, sem paralelo de FFmpeg, separação vocal, RVC ou render. Downloads de produção também são seriais. Descoberta e classificação leve podem continuar em segundo plano, desde que não baixem mídia nem disputem CPU/memória dos modelos. Limites de lote, tempo e orçamento são persistidos e configuráveis; aumentos exigem medição no notebook.

## START ALL

`START_ALL.bat` é o único ponto de entrada de usuário. Confere `.venv` 3.11.9, credenciais e preflight dos módulos/runtime; por padrão valida, sem iniciar produção, Bot API, buscas Shopee ou publicação. O launcher do Coordinator e as ferramentas de auditoria ficam em `scripts/` e são componentes internos, não atalhos de produção.

## Validação de entrega

Valide no `.venv` novo:

1. `python -m pip check` sem conflitos.
2. Suíte completa com `python -m pytest`.
3. Preflight integrado `START_ALL.bat` sem argumento, sem conexão comercial ou publicação.
4. Integridade SQLite: `PRAGMA quick_check` igual a `ok` e `PRAGMA foreign_key_check` vazio em cada banco copiado.
5. Migração idempotente na cópia nova; confirmar estados, eventos, publicações, hashes e recibos preservados.
6. Fluxo de descoberta/Vision sem criar pastas por item; provar materialização unitária em Stock e execução serial de Speech/Studio.
7. `python scripts/verify_installation.py` confirma branch, commit, árvore limpa e igualdade com `origin/main`; gera hashes SHA-256 dos arquivos versionados em `storage/validation/source-integrity.json` e recusa arquivos privados.
8. Revisão de `git status` e arquivos ignorados para garantir que não haja credenciais, sessões, bancos, mídia ou modelos no Git.

Na validação local Windows, quatro testes podem ser ignorados por barreiras explícitas do ambiente: o E2E configurável que pode fazer uma publicação real, dois testes de links simbólicos que exigem privilégio do Windows, e a verificação de `safe_globals` quando a API pública não existe na versão de PyTorch instalada. Esses skips não afirmam validação de publicação real; envios reais de certificação dependem de autorização explícita.

O projeto só deve ser declarado pronto quando a validação integrada e a instalação reproduzível forem aprovadas. Evidências transitórias de validação ficam em `storage/validation/` e não são versionadas. Este documento é a única documentação técnica do repositório; o README raiz é somente uma apresentação curta. Relatórios antigos do laboratório de áudio foram consolidados como evidência histórica abaixo e não são validação da versão Definitivo.


## Contratos operacionais adicionais

### Legendas ArmoredIA

A primeira linha da legenda deve começar por um único coração laranja (`🧡`), seguido por uma descrição curta e natural do produto. A normalização pode corrigir posição e duplicidade do coração, espaços e formato das hashtags, mas a Policy também avalia coerência com o contexto aprovado, português brasileiro, alegações não comprovadas e pertinência das hashtags. Rejeições acionam nova tentativa limitada; não se aprova texto só por cumprir formatação.

### Pipeline de áudio e vídeo

O Speech executa a classificação e toda decisão de áudio, inclusive RVC Melody e efeitos sonoros, conforme o contrato de áudio v5 validado. Entrega ao Studio uma trilha final pronta. O Studio recebe essa trilha, executa somente o plano visual e muxagem final, preserva o original e valida o MP4 por FFprobe. O Coordinator não inicia mais de um item pesado simultaneamente.

### Telegram Bot API local

O executável nativo e suas DLLs ficam em `runtime/telegram-bot-api/`; não exigem outro ambiente Python. `BOT_API_EXE` e `BOT_API_WORKDIR` são caminhos relativos à raiz em `credentials/project.env`. O START verifica a porta e autentica com `getMe`; só encerra o processo cuja propriedade registrou quando ele próprio iniciou o servidor. Estado local de execução permanece em `storage/logs/`.

### Organização e portabilidade

A raiz contém apenas os pontos de entrada, metadados do projeto e os diretórios funcionais principais. Wheels RVC/Fairseq necessários ao bootstrap estão em `runtime/packages/` e referenciados pelo lock; pesos, executáveis locais, banco, sessões e credenciais ficam ignorados pelo Git. O Bot API local fica no runtime. O pytest escreve seu cache dentro de `storage/validation/`. O bootstrap instala o pacote sem modo editável, evitando gerar `armoredcreator.egg-info` na raiz. O README é só um guia breve; este documento é a única documentação em `docs/`.

### Limites da validação atual

Testes automatizados e preflight local não substituem certificação real com os serviços externos. O teste real `tests/e2e/test_real_telegram.py` também exige `ARMORED_REAL_TELEGRAM_E2E=1`, `ARMORED_REAL_PUBLICATION_AUTHORIZED=1` e `ARMORED_REAL_PUBLICATION_TOPIC_ID` com um dos destinos contratuais; ele pode publicar um item real uma única vez. Nenhuma publicação nova é permitida sem autorização específica para a certificação do Definitivo; consultas comerciais permanecem condicionadas à quota/orçamento válido. Os recibos das publicações antigas são evidência histórica e nunca devem ser apagados para permitir republicação.


### Evidência histórica de Speech → Studio

A implementação de referência no ArmoredAudioLab registrou um corpus real de 17 vídeos concluído no contrato v5, com originais intactos e saídas H.264 vertical/AAC; houve também um caso real de banner aprovado pelo usuário. Uma revisão auditiva anterior registrou 15 rótulos humanos de áudio. Esses resultados justificam a referência e os contratos reutilizados, mas são evidências da instalação/laboratório anterior; não certificam o runtime Definitivo. Os testes desta instalação usam dados sintéticos e não baixam vídeos de Telegram nem publicam conteúdo. Para certificação definitiva, ainda é necessária validação real controlada, sem envios até autorização específica.

## Estrutura operacional

`runtime/telegram-bot-api/` contém apenas o executável nativo e DLLs locais; `runtime/models/` contém modelos ignorados pelo Git; `runtime/packages/` contém somente as wheels/fontes necessárias ao bootstrap; `storage/database/`, `videos/`, `logs/`, `backups/` e `validation/` separam os dados de execução e evidências. `credentials/` concentra tokens, chaves e sessões. O cache do pytest fica em `storage/validation/.pytest_cache/`. Não há `.env` de produção na raiz, clone auxiliar ou arquivo de teste no diretório raiz.

## Certificação operacional — 25/10/2026

Este retrato registra evidências da instalação local, sem declarar a Fase 15 concluída.

| Verificação | Resultado observado |
| --- | --- |
| `START_ALL.bat` sem argumentos | Preflight de runtime, montagem dos sete módulos, integridade SQLite e configuração das três fontes/rotas aprovados. |
| Dependências | `pip check` sem conflitos. |
| Suíte local | 759 aprovados, 4 ignorados, 0 falhas. Os ignorados são o E2E configurável de publicação, dois testes que exigem privilégios para links simbólicos e o teste de `safe_globals` indisponível nesta versão do PyTorch. |
| Banco principal | `PRAGMA quick_check = ok`; `foreign_key_check` sem violações. |
| Publicações por rota | Recibos confirmados: tópico 1327 / mensagem 1359; tópico 228 / mensagem 1360; tópico 1160 / mensagem 1361; todos no chat `-1004341972306`. |
| Produção real pelo `START_ALL` | Item `-1003788989075_298` percorreu recuperação de Speech/RVC, Studio e Hub pelo launcher; MP4 H.264/AAC 1080×1920 validado pelo FFprobe e publicação confirmada no tópico 228. A legenda já estava persistida antes desta execução. |
| Produção real com Ollama/Gemma | Item `-1002698134896_30` percorreu Policy, Speech/RVC Melody, Studio, FFprobe e Hub usando Gemma; MP4 H.264/AAC 1080×1920 validado e publicação confirmada no tópico 1160. Este ensaio foi iniciado pelo Coordinator diretamente, não por `START_ALL`. |
| Descoberta Telegram | As três fontes foram consultadas. Um item novo sem link comercial, `-1002039708059_12043`, foi registrado como `WAITING_VISION`; o original não foi baixado. Amostras posteriores encontraram candidatos com link nas fontes 2 e 3. |

As evidências estruturadas e os hashes dos dois MP4s ficam no arquivo ignorado `storage/validation/operational-certification-2026-10-25.json`. O banco indica que a sincronização histórica ainda não chegou ao fim nas três fontes. Não foi feita nova consulta comercial: não havia ledger de quota persistente Shopee válido. Por isso, a aprovação Vision de um novo item Shopee continua sem certificação nesta instalação.

Continuam pendentes: executar o fluxo Gemma completo pelo próprio `START_ALL.bat`; concluir uma consulta Vision real sob orçamento persistente autorizado; ensaiar interrupção/retomada deliberada em todas as etapas críticas; medir uma operação prolongada no notebook-alvo; instalar e iniciar em ambiente limpo; concluir reconciliação do histórico; e regenerar `source-integrity.json` após sincronizar uma árvore limpa com o commit publicado. A recuperação de Speech/RVC foi observada em uma execução real e há cobertura automatizada para outros cenários, mas isso não substitui a matriz operacional de interrupções.
