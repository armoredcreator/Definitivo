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
| ArmoredVision | Resolver produto/oferta, identidade Shopee, link afiliado, contexto de produto e aprovação. Consultas são feitas para produtos exatos necessários à fila; a API da Shopee continua podendo impor sua própria taxa/quota. |
| ArmoredStock | Materializar o original de um único item aprovado, criar workspace, validar arquivo e SHA-256. |
| ArmoredIA | Gerar legendas editoriais localmente a partir de regras e fatos persistidos pela Vision, sem depender de Ollama ou Gemini. Validar sentido, contexto e hashtags; a legenda aprovada contém exatamente um 🧡 no início. |
| ArmoredSpeech | Único dono de extração, classificação de áudio, decisão de rota, RVC Melody, efeitos, volumes e trilha final. `PT_BR_NARRATION → RVC Melody`; música/idioma estrangeiro/sem áudio seguem a política aprovada de silenciar o original e aplicar efeito. |
| ArmoredStudio | Apenas análise/tratamento visual, crop 9:16, montagem MP4 e integração da trilha final do Speech. Não classifica áudio nem executa RVC; FFprobe valida o resultado. |
| ArmoredHub | Publicar somente pelo comando explícito, persistir recibo e reconciliar resultado. Nenhum envio real acontece no preflight. |

O Coordinator integra os módulos e impõe a sequência. Discovery leve pode ocorrer durante produção se não competir pelos recursos pesados. Todo caminho de materialização e processamento em catch-up deve selecionar somente um item; Speech/Studio recebem listas unitárias.

## Estados e retorno para Stock

Vision aprovado é representado pelo item `RECEIVED` com `affiliate_url` persistida. A migração `20261024_001_requeue_approved_to_stock` foi corrigida para nunca alterar `PUBLISHED`, `PUBLISHING` ou itens com recibo de publicação. A migração corretiva `20261024_002_restore_publication_fences` usou os eventos preservados para restaurar 15 itens com recibo `CONFIRMED` ao estado terminal `PUBLISHED`. Sete itens com publicação pendente, enviada sem verificação ou etapa de envio sem recibo voltaram para `RECOVERY`. A migração `20261024_003_fence_missing_legacy_receipts` criou travas duráveis para os três casos `PUBLISHING` sem recibo; a quarentena local contém oito itens ambíguos no total, incluindo recibos pendentes fora do conjunto de 23. Nenhum deles pode voltar automaticamente à produção ou ser reenviado. Um `RECOVERY` sem recibo e sem histórico de envio retornou a `RECEIVED` para aguardar Stock.

A primeira migração havia reencaminhado **23 itens** (15 `PUBLISHED`, 5 `PUBLISHING`, 3 `RECOVERY`) e limpado referências derivadas; o backup original preservou os estados e evidências anteriores. A correção foi aplicada somente na cópia nova em 24/10/2026 e alterou 22 estados: 15 `PUBLISHED`, 7 `RECOVERY`; o item restante, `RECOVERY` sem recibo e sem histórico de envio, continuou em `RECEIVED`. Os 20 recibos e todos os eventos anteriores permanecem preservados; nada foi apagado dos tópicos. As correções são idempotentes, registradas em `migration_audit` e precedidas por backups consistentes do SQLite.

O histórico de publicação não autoriza apagar mensagens de tópicos. O código não executa exclusão de mensagens nem envia Telegram no START/preflight. Itens em quarentena continuam bloqueados até reconciliação apropriada.

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

`START_ALL.bat` sem argumento executa preflight e validação de configuração. `--run` faz um lote único e limitado; `--continuous` processa a coleta histórica em lotes retomáveis, sem limite diário de itens, e permanece em LIVE depois que a varredura histórica e a fila elegível terminam. O tamanho do lote é somente uma fronteira de checkpoint, não um teto total. Hub real requer `--publish`. Vision não usa orçamento temporário local; erros de taxa ou quota devolvidos pela própria Shopee continuam sendo respeitados.

## Operação e recovery

O SQLite é a fronteira de retomada. Antes de processar, valide configuração, integridade do banco, fontes, espaço e modelos. Sync/ Vision persistem decisões e checkpoints. Stock baixa um item aprovado por vez; original é imutável e validado por hash. Artefatos incompletos são preservados com recibo para inspeção. IA, Speech e Studio salvam progresso com identidade do item. Hub registra tentativa e recibo; resultado incerto permanece em `RECOVERY`/quarentena até reconciliação e nunca é tratado como ausência confirmada.

Não apague `.part`, arquivos de resultado, recibos, quarentenas ou checkpoints manualmente. Refaça preflight e use os comandos de recuperação descritos pelo CLI. Backups de SQLite devem usar a API de backup, especialmente com WAL ativo. Mantenha a cópia anterior até confirmar o funcionamento da nova versão.

## Recursos do notebook

O limite de concorrência de produção é estrito: um vídeo por vez, sem paralelo de FFmpeg, separação vocal, RVC ou render. Downloads de produção também são seriais. Descoberta e classificação leve podem continuar em segundo plano, desde que não baixem mídia nem disputem CPU/memória dos modelos. A operação contínua não tem teto diário de itens; lotes persistidos permitem retomada sem interromper o catch-up à meia-noite.

## START ALL

`START_ALL.bat` é o único ponto de entrada de usuário. Confere `.venv` 3.11.9, credenciais e preflight dos módulos/runtime; sem argumentos, não inicia produção nem publicação. Para continuar até concluir o histórico e seguir em LIVE, no PowerShell use:

```powershell
Set-Location 'C:\Users\Administrador\Downloads\Definitivo'
.\START_ALL.bat --continuous --publish --continuous-operation-id historico-live-20261025
```

### Validação de legendas locais — 26/10/2026

O provedor operacional de legendas foi alinhado ao Ollama local com `qwen2.5:1.5b`, adequado à memória limitada do notebook. A saída estruturada deixou de impor uma lista rígida de palavras ao texto gerado: essa restrição fazia o modelo preencher a frase com termos desconexos. O esquema agora limita o tamanho; a Policy compartilhada continua validando suporte no contexto Vision, tom, texto e hashtags.

Foi ampliada a extração de fatos curtos da Vision para cobrir atributos estruturados além das expressões já conhecidas. Quando o Qwen ou a Policy não produzem uma candidata válida, o gerador pode usar apenas um fragmento literal da Vision e uma hashtag de categoria; sem fato confiável, a geração falha de forma segura.

Ensaio local real no notebook, sem chamadas externas e sem publicação: o prompt Ollama foi simplificado para um detalhe curto da Vision e JSON simples. O Qwen 2.5 1.5B gerou diretamente 3 de 3 legendas em categorias diferentes e todas passaram pela Policy: “Divisórias modulares” (`#organizador`), “Braço articulado” (`#luminaria`) e “Manga curta” (`#camiseta`). Cada item usou uma chamada local, entre 4,7 e 10,5 segundos; nenhum fallback foi selecionado. A Policy reconhece `camiseta` como categoria e preserva essa hashtag validada. A validação automatizada direcionada a legendas/Ollama passou com 104 testes, 0 falhas. A suíte geral passou com 811 aprovados e 4 ignorados, excluído somente `test_startup_preserves_interrupted_download_before_rediscovery`, que continua pendente. Este ensaio de legendas não certifica o fluxo Telegram/Speech/Studio.

O tamanho interno padrão dos lotes é 25 itens; ele não limita o total. O Coordinator ainda processa um vídeo pesado por vez. `--publish` habilita envios reais aos tópicos configurados. Se o processo fechar, execute novamente o mesmo comando e o mesmo ID para retomar os checkpoints. O launcher do Coordinator e as ferramentas de auditoria ficam em `scripts/` e são componentes internos, não atalhos de produção.

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

A primeira linha da legenda deve começar por um único coração laranja (`🧡`), seguido por uma observação curta, natural e baseada em um fato confirmado pela Vision. Não é necessário declarar benefício. Mencionar o nome comum ou a categoria do produto é opcional: só deve acontecer quando deixar a frase mais clara e continuar natural. Não se força uma abertura fixa nem se conectam atributos sem relação confirmada. A normalização pode corrigir posição e duplicidade do coração, espaços e formato das hashtags, mas a Policy também avalia coerência com o contexto aprovado, português brasileiro, alegações não comprovadas e pertinência das hashtags. Rejeições acionam nova tentativa limitada; não se aprova texto só por cumprir formatação.

### Pipeline de áudio e vídeo

O Speech executa a classificação e toda decisão de áudio, inclusive RVC Melody e efeitos sonoros, conforme o contrato de áudio v5 validado. Entrega ao Studio uma trilha final pronta. O Studio recebe essa trilha, executa somente o plano visual e muxagem final, preserva o original e valida o MP4 por FFprobe. O Coordinator não inicia mais de um item pesado simultaneamente.

### Telegram Bot API local

O executável nativo e suas DLLs ficam em `runtime/telegram-bot-api/`; não exigem outro ambiente Python. `BOT_API_EXE` e `BOT_API_WORKDIR` são caminhos relativos à raiz em `credentials/project.env`. O START verifica a porta e autentica com `getMe`; só encerra o processo cuja propriedade registrou quando ele próprio iniciou o servidor. Estado local de execução permanece em `storage/logs/`.

### Organização e portabilidade

A raiz contém apenas os pontos de entrada, metadados do projeto e os diretórios funcionais principais. Wheels RVC/Fairseq necessários ao bootstrap estão em `runtime/packages/` e referenciados pelo lock; pesos, executáveis locais, banco, sessões e credenciais ficam ignorados pelo Git. O Bot API local fica no runtime. O pytest escreve seu cache dentro de `storage/validation/`. O bootstrap instala o pacote sem modo editável, evitando gerar `armoredcreator.egg-info` na raiz. O README é só um guia breve; este documento é a única documentação em `docs/`.

### Limites da validação atual

Testes automatizados e preflight local não substituem certificação real com os serviços externos. O teste real `tests/e2e/test_real_telegram.py` também exige `ARMORED_REAL_TELEGRAM_E2E=1`, `ARMORED_REAL_PUBLICATION_AUTHORIZED=1` e `ARMORED_REAL_PUBLICATION_TOPIC_ID` com um dos destinos contratuais; ele pode publicar um item real uma única vez. A publicação real de certificação da mensagem 1363 ocorreu em 25/10/2026 com autorização explícita do operador; outras publicações também exigem autorização específica. Consultas comerciais permanecem condicionadas à quota/orçamento válido. Os recibos das publicações antigas são evidência histórica e nunca devem ser apagados para permitir republicação.


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
| Suíte local | 777 aprovados, 4 ignorados, 0 falhas após a otimização do seed histórico. Os ignorados são o E2E configurável de publicação, dois testes que exigem privilégios para links simbólicos e o teste de `safe_globals` indisponível nesta versão do PyTorch. |
| CI remoto | O commit `20f13e1` concluiu o workflow `Definitivo CI` no Windows com 779 testes aprovados, 2 ignorados e 0 falhas. Esta revisão do documento mestre não altera código/testes. |
| Banco principal | `PRAGMA quick_check = ok`; `foreign_key_check` sem violações. Reconciliação somente leitura com a base congelada: 14.486 itens ativos + 5.480 arquivados = 19.966 IDs históricos; os 19.966 permanecem na base Definitivo, com zero diferença nos 5.480 payloads arquivados/hashes, 78.074 eventos e 20 recibos antigos. Definitivo tem 14.487 ativos + 5.480 arquivados e apenas um ID adicional novo (`-1002039709075_12043`); preservação histórica aprovada. |
| Publicações por rota | Verificação ao vivo dos recibos: tópico 1327 / mensagem 1359; tópico 228 / mensagens 1360 e 1363; tópico 1160 / mensagem 1361; todos no chat `-1004341972306`. |
| Produção real pelo `START_ALL` | Item `-1003788989075_298` percorreu recuperação de Speech/RVC, Studio e Hub pelo launcher; MP4 H.264/AAC 1080×1920 validado pelo FFprobe e publicação confirmada no tópico 228. A legenda já estava persistida antes desta execução. |
| Produção real com Ollama/Gemma | Item `-1002698134896_30` percorreu Policy, Speech/RVC Melody, Studio, FFprobe e Hub usando Gemma; MP4 H.264/AAC 1080×1920 validado e publicação confirmada no tópico 1160. Este ensaio foi iniciado pelo Coordinator diretamente, não por `START_ALL`. A legenda anterior (`Bolsa de computador`) foi substituída nesta certificação por `🧡 Compartimento pro almoço` / `#bolsa #almoço`, aprovada pela Policy e aplicada à mesma mensagem 1361 sem reenviar o vídeo; a confirmação ao vivo e o recibo foram preservados. |
| Legenda e mídia pelo `START_ALL.bat` | Lote de um item para `-1003788989075_299` executado com Gemma 3 1B. A Policy recusou duas saídas sem suporte; o fallback baseado no texto Vision aprovou `🧡 Esfoliante para banho` / `#esfoliante #banho`. Stock copiou o original da instalação antiga para o storage canônico, verificando o SHA-256 e mantendo a origem intacta. Speech/RVC Melody, Studio v5 e FFprobe concluíram; o MP4 H.264/AAC 1080×1920 de 10 s foi validado. Após o dry-run inicial, a busca exata no tópico 228 encontrou zero publicação prévia; o mesmo lote persistente foi retomado por `START_ALL.bat --publish`, resultando na mensagem 1363, recibo confirmado, estado `PUBLISHED` e limpeza concluída. |
| Edição das três legendas já publicadas | As mensagens 1359 (tópico 1327), 1360 (tópico 228) e 1361 (tópico 1160) foram verificadas ao vivo antes da edição. A Policy aprovou as legendas atualizadas; o Bot API editou somente as legendas, preservou vídeos, links afiliados, tópicos e recibos, e as três mensagens foram confirmadas novamente ao vivo. Backup SQLite anterior às alterações em `storage/validation/armoredcreator-before-caption-edits-20261025-092040.db`. Evidência estruturada no relatório de legendas. |
| Descoberta Telegram | As três fontes foram consultadas. Um item novo sem link comercial, `-1002039708059_12043`, foi registrado como `WAITING_VISION`; o original não foi baixado. Amostras posteriores encontraram candidatos com link nas fontes 2 e 3. |
| Seed de identidade histórica | O primeiro seed operacional registrou 8.258 identidades em `product_identity_claims`, sem alterar estados nem baixar mídia. A revisão calcula hashes somente quando originais competem pela mesma identidade e faixa de prioridade; identidades únicas dispensam leitura de vídeos. |
| Vision real Shopee | Uma chamada com orçamento persistente para `-1002039708059_12030` resolveu a identidade exata, consumiu 1 de 2 slots e retornou `NO_AFFILIATE_OFFER`. O item permanece corretamente em `WAITING_VISION`; não houve download nem produção. Evidência e limite do orçamento no relatório local de certificação. |
| Legendas baseadas em Vision | Após o preflight do `START_ALL.bat`, o gerador e a Policy compartilhada foram executados sobre contextos Vision reais e persistidos. As três frases aprovadas passaram sem chamada ao provedor. Em `-1003788989075_299`, Gemma 3 1B fez duas inferências; a Policy recusou a saída do modelo e o fallback factual `🧡 Esfoliante para banho` foi aprovado. Também foram aprovados fallbacks para vestido, sutiã, moletom, pijama e sandália em contextos históricos reais. A avaliação do gerador não fez consulta comercial nem envio Telegram; a publicação real posterior do item 299 está descrita acima. Evidência: `storage/validation/caption-grounded-certification-2026-10-25.json`. |

As evidências estruturadas e os hashes dos dois MP4s ficam no arquivo ignorado `storage/validation/operational-certification-2026-10-25.json`. O banco indica que a sincronização histórica ainda não chegou ao fim nas três fontes. A consulta Shopee real ficou registrada em orçamento persistente, mas o produto não tinha oferta afiliada exata; portanto, a aprovação de um novo item continua pendente. O item foi mantido em `WAITING_VISION` sem baixar a mídia.

Continuam pendentes: aprovar um novo item Vision com oferta afiliada válida; ampliar a avaliação de naturalidade/cobertura das legendas além das categorias amostradas; executar a matriz operacional de interrupção e retomada; medir operação prolongada no notebook-alvo; e comprovar uma instalação limpa/portabilidade em outra máquina. A reconciliação histórica, a sincronização com `origin/main`, a integridade dos 267 arquivos versionados e o CI do commit de código `20f13e1` foram concluídos. A correção de request count e o seed otimizado estão cobertos pela suíte local de 777 testes aprovados; a primeira execução ponta a ponta registrou o contador pelo comportamento anterior, diferença descrita na evidência local.


### Complemento de certificação — 25/10/2026

| Verificação adicional | Resultado observado |
| --- | --- |
| Policy de legendas | Corrigida a concordância de gênero/número para bebidas e temperaturas; regressão de `Cafe quentes elegante` coberta por teste. `tests/test_caption_policy.py`: 64 aprovados. Suíte completa após a correção: 777 aprovados, 4 ignorados, 0 falhas. |
| Instalação isolada | Checkout limpo no mesmo notebook, bootstrap com Python 3.11.9, lock de runtime, credenciais/modelos provisionados fora do Git e bancos copiados pela API SQLite; `pip check` e `START_ALL.bat` aprovados. Suíte na cópia: 777 aprovados, 4 ignorados, 0 falhas. Isso não equivale a uma segunda máquina física. |
| Item novo de ponta a ponta | `-1002039708059_12045`: Vision encontrou oferta válida; Stock baixou somente após aprovação e conferiu SHA-256 `da826d213fbeaa7931a2432da6d19365d91c2ce2f51d481d641adbfcbc6eefff`; Policy aprovou `🧡 Bebidas quentes ou frias` / `#cafe #inox`; Speech/Melody e Studio concluíram; FFprobe validou MP4 H.264/AAC vertical de 19,4 s. Hub publicou no chat `-1004341972306`, tópico 1327, mensagem 1364. Recibo `CONFIRMED`, estado `PUBLISHED`, limpeza concluída; consulta ao Telegram confirmou vídeo, tópico, legenda e URL afiliada. |
| Descoberta real incremental | As três fontes responderam. O item `-1002039708059_12044` sem link ficou em `WAITING_VISION`, sem download. `-1002039708059_12046` tem oferta aprovada e segue em `RECEIVED`, ainda sem download/produção. Dois candidatos duplicados da fonte 1 foram reconhecidos antes de Vision/Stock e não consumiram download nem consulta comercial. |
| Interrupção e retomada observada | Uma execução do item 12045 foi encerrada por falha de codificação ao imprimir o relatório final, após gerar o MP4 em dry-run e persistir o progresso. A retomada voltou de `PUBLISHING`, reutilizou o artefato e publicou uma única vez; recibo e consulta ao tópico confirmaram o resultado. Isso demonstra esse cenário específico, não uma matriz completa de interrupções. |
| Integridade dos bancos ativos | Os sete bancos em `storage/database/` passaram `PRAGMA quick_check = ok` e `PRAGMA foreign_key_check` vazio. Banco principal: 14.501 itens — 20 `PUBLISHED`, 8 `RECOVERY`, 8.239 `RECEIVED`, 6.229 `WAITING_VISION` e 5 `DUPLICATE`. |
| Sincronização histórica | **Pendente.** Duas leituras retomáveis; a primeira inseriu mensagens novas e a segunda foi idempotente, mas ambas foram interrompidas sem completar a varredura. As três fontes continuam `historical_complete=0`. |
| Estabilidade prolongada | **Pendente.** Uma produção real foi concluída; a memória de trabalho observada nessa execução chegou a aproximadamente 2,7 GB. Não foi executado ensaio prolongado de descoberta/produção concorrentes no notebook. |
| Portabilidade | **Parcial.** Bootstrap reproduzido em checkout isolado no mesmo notebook; não houve segundo computador Windows para validar portabilidade física. |
| CI remoto do commit `7563493` | **Aprovado.** Workflow `Definitivo CI` no Windows: execução 40200127503 concluída com sucesso. A instalação local foi comparada com `origin/main` pelo verificador de integridade. |

Evidência estruturada: `storage/validation/completion-certification-2026-10-25.json` (local, ignorada pelo Git). A sincronização histórica e o ensaio prolongado são requisitos remanescentes; a Fase 15 não está certificada como concluída.


### Atualização de certificação — 25/10/2026

| Verificação | Resultado observado |
| --- | --- |
| Varredura histórica Sync | Concluída sem erros (`varredura=OK`): 6.645 candidatos examinados nas três fontes — F1 `-1003788989075`: 0 novos, F2 `-1002698134896`: 3.373, F3 `-1002039708059`: 3.272. Sync registrou itens e duplicados sem baixar mídia. O banco passou de 14.501 para 21.087 itens ativos. |
| Duplicados anteriormente arquivados | A auditoria detectou que 5.480 IDs compactados haviam sido reabertos pelo Sync; 4.255 estavam indevidamente `RECEIVED`. O backup `storage/backups/armoredcreator-before-archived-sync-repair-20261025T143630Z.sqlite3` foi criado e validado antes da reparação. A migração `20261025_004_fence_reingested_archived_duplicates` colocou os 5.480 em `DUPLICATE`, preservou intactos os 5.480 snapshots arquivados e gravou auditoria/eventos. A nova proteção em `Database.reserve_item` verifica hash, identidade e proprietário arquivado e impede reabrir esse trabalho. |
| Banco após reparação | 21.087 itens ativos: 5.991 `DUPLICATE`, 20 `PUBLISHED`, 8.898 `RECEIVED`, 8 `RECOVERY`, 6.170 `WAITING_VISION`. Todos os sete bancos passaram `quick_check=ok` e `foreign_key_check` vazio. Os 5.480 itens ainda presentes no arquivo aparecem ativos somente como `DUPLICATE`; nenhum foi enviado ao Vision/Stock pela varredura. |
| START_ALL após reparação | Preflight de runtime, composição, SQLite, credenciais e três rotas contratuais aprovados. |
| Suíte local após a correção | 779 aprovados, 4 ignorados, 0 falhas. Os ignorados permanecem as duas barreiras do Windows, `safe_globals` indisponível e E2E Telegram que exige configuração do runner. |
| CI remoto | O commit `2815755` passou no Windows: 781 aprovados, 2 ignorados, 0 falhas. Workflow `Definitivo CI`, execução 40203220036. |
| Corte para LIVE e processamento do backlog | **Pendente.** As três flags `historical_complete` continuam em zero porque Sync foi executado como etapa de descoberta isolada. Ainda há itens `RECEIVED` para Vision, `RECOVERY` para reconciliação e limites persistentes de consultas Shopee. O fluxo não deve iniciar Vision em massa nem mudar para LIVE até completar as etapas seguintes e seus orçamentos autorizados. |
| Recibo histórico não confirmado | O item `-1003788989075_1040`, recibo Telegram 1339/tópico 228, foi consultado ao vivo por ID e o Hub retornou `ABSENT`. O registro tem campos históricos inconsistentes (`confirmed=1`, `SENT_UNVERIFIED`) e permanece em `RECOVERY`; o recibo e a quarentena foram preservados, sem novo envio. |
| Operação prolongada / outro PC | Ainda pendentes: ensaio contínuo controlado de descoberta/produção e validação física em uma segunda máquina Windows. A instalação isolada no mesmo notebook passou bootstrap, `START_ALL.bat` e 779 testes. |

A evidência estruturada local foi atualizada em `storage/validation/completion-certification-2026-10-25.json`. A varredura Sync histórica agora está comprovada; a Fase 15 continua aberta até Vision/produção do backlog dentro dos limites, resolução segura dos recibos em `RECOVERY`, teste prolongado, portabilidade em outra máquina e CI da correção mais recente.


### Revalidação da instalação isolada — 25/10/2026

Após a proteção contra duplicados arquivados, o checkout isolado no mesmo notebook repetiu a suíte completa com 779 aprovados, 4 ignorados e 0 falhas; `START_ALL.bat` passou com os sete módulos, configuração e bancos daquela cópia. O SQLite dessa instalação de teste é um snapshot operacional anterior à varredura histórica ampliada. O banco operacional atualizado foi validado separadamente após a migração: sete bancos íntegros, sem violações FK, e `START_ALL.bat` aprovado. A validação em outra máquina física continua pendente.


### Correção operacional — velocidade de narração e formato vertical — 25/10/2026

O áudio original do item `-1002039708059_12046` foi medido em 373,1 palavras por minuto na amostra inicial de oito segundos. Esse valor ultrapassa o limite operacional de 230 palavras por minuto para RVC. O registro persistente do ArmoredSpeech foi corrigido para `PT_BR_NARRATION_UNSUITABLE`, `rvc_eligible=0`; novas análises aplicam o mesmo bloqueio a qualquer narração em português que ultrapasse o limite ou cuja velocidade não possa ser medida. A rota resultante silencia a voz original e mantém o efeito sonoro do projeto.

A auditoria dos 26 itens publicados e dos sete registros Speech previamente elegíveis ao RVC cobriu 27 originais únicos. Dois excederam o limite: `-1002039708059_12046` (373,1 WPM) e `-1003788989075_296` (239,4 WPM). O classificador real confirmou ambos como `PT_BR_NARRATION_UNSUITABLE`. Os outros 25 não foram classificados como narração rápida em português. O item 296 continua em `RECEIVED`, sem resultado nem publicação; seu registro de Speech foi atualizado para impedir que uma retomada reutilize a aprovação RVC antiga. O relatório local `storage/validation/rvc-speech-rate-audit-2026-10-25.json` registra velocidades, confiança de idioma e a decisão por item. Cópias do banco Speech anteriores às duas correções: `storage/backups/armoredspeech-before-fast-speech-reclassification-20261025-194115.sqlite3` e `storage/backups/armoredspeech-before-fast-speech-reclassification-296-20261025-194913.sqlite3`.

A mídia da mensagem Telegram `1369` foi substituída no mesmo chat e tópico (`-1004341972306`, tópico `1327`), sem novo envio. A edição preservou a legenda e o link afiliado. O arquivo efetivo usa H.264/AAC, 1080×1920, proporção 9:16; o Bot API respondeu com dimensões 1080×1920. O quadro extraído confirma que a imagem ocupa a tela vertical. O resultado local persistido aponta para a versão sem narração e com efeito sonoro. Backup do banco principal anterior à atualização: `storage/backups/armoredcreator-before-1369-effect-only-20261025-193801.sqlite3`.

A base congelada confirma o contrato visual de saída 1080×1920, mantendo a proporção e aplicando crop quando necessário; essa regra foi seguida nesta correção. As saídas locais disponíveis de todos os itens publicados também foram verificadas com FFprobe: 11 de 11 estão em 1080×1920 (9:16). O `ModelProcessor` executado sobre o original 12046 confirmou `PT_BR_NARRATION_UNSUITABLE`, `speech_rate_wpm=373.1` e `rvc_eligible=false`. A suíte completa passou localmente com 802 aprovados, 4 ignorados e 0 falhas; `START_ALL.bat` aprovou Audio Preflight, composição dos sete módulos, SQLite e configuração das três fontes/rotas. No GitHub, o CI principal do commit `4d14ed0` concluiu com sucesso (run `40241607053`), assim como o diagnóstico real de áudio (run `40241607045`). Esta correção não fecha os requisitos remanescentes de operação prolongada e portabilidade em outro computador, descritos acima.

### Atualização operacional — execução contínua sem teto diário

O modo contínuo agora usa lotes persistidos somente como fronteiras de retomada. Não existe limite diário de itens; com `--publish`, a execução processa a coleta histórica elegível até os três históricos terminarem e então segue monitorando as fontes em LIVE. O processamento pesado permanece serial, um vídeo por vez. Itens sem link/oferta utilizável podem permanecer em `WAITING_VISION`, e respostas de rate limit/quota da própria Shopee continuam sendo respeitadas.

O orçamento local de consultas Shopee usado em ensaios anteriores não é mais exigido nem controla Vision. Os registros SQLite antigos foram mantidos como histórico; o runtime não os consulta. O parâmetro `--max-items-per-day` foi removido. Para iniciar ou retomar a operação real, use o mesmo `--continuous-operation-id` e `--publish`:

```powershell
Set-Location 'C:\Users\Administrador\Downloads\Definitivo'
.\START_ALL.bat --continuous --publish --continuous-operation-id historico-live-20261025
```

### Reavaliação de entrega e legendas — 28/10/2026

Esta seção registra a auditoria mais recente do checkout operacional. Ela substitui qualquer conclusão anterior de que a entrega estaria pronta; o contrato permanece aberto.

| Área | Evidência atual | Pendência |
| --- | --- | --- |
| Publicações e legendas | Há 79 recibos confirmados no banco. A reavaliação pela Policy presente no checkout encontrou 15 legendas reprovadas: mensagens 1397, 1405, 1412, 1413, 1419, 1420, 1424, 1430–1437. Outras 64 passam pelo filtro formal, sem garantia de naturalidade ou aderência semântica. | Nenhuma legenda antiga foi editada; todas continuam aguardando revisão. A mensagem 1431 permanece com `#chinelo` para uma pantufa. A revisão deve também cobrir 1384 e as mensagens 1432–1438, que não estão no material anterior. |
| Falsos aprovados observados | A mensagem 1437 expõe “Miriam” e contém frase promocional/confusa; 1432 usa `#Fino` sem identificar o produto; 1435 usa nome de linha e frase pouco clara. A mensagem 1364 (“O display digital”) parece fragmentária; 1408 usa `#cano` para meias. | A aprovação formal não deve ser tratada como aprovação editorial. A Policy agora exige uma hashtag correspondente à categoria principal conhecida e rejeita rótulos nominais incompletos sem predicado. O gerador prioriza legendas locais compostas de fatos Vision; Qwen fica como alternativa quando não há fallback seguro. As alterações ainda precisam de validação direcionada e avaliação editorial das frases, marcas/linhas e demais tags. |
| Opções locais | Na reavaliação informada em 28/10 do material gerado pelo Qwen para 71 produtos, 25 opções passam pela Policy em 21 produtos; 50 produtos não têm opção aprovada nesse material. Doze tentativas de feedback ficaram adiadas. | O relatório anterior não certifica cobertura total nem correção de todas as publicações. Regerar/revisar os itens sem candidata válida, incluindo os ausentes do relatório. |
| Inicialização e fluxo integrado | `START_ALL.bat` passou preflight de áudio, composição dos sete módulos, configuração das três fontes/rotas e autenticação Bot API em modo contínuo com publicação. O item do óleo percorreu IA, Speech, Studio e Hub; a mensagem 1438 foi confirmada no tópico 228 com `🧡 Nutrição em óleo #oleo`. A suíte focada em legendas/provedores passou com 224 testes. | Um fluxo concluído demonstra integração nesse item, não qualidade consistente do Qwen nem operação contínua confiável. |
| Recovery de IA | O item 422 acumulou 28 tentativas de recuperação antes de voltar à IA. O item 424 teve dez opções rejeitadas e retornou à IA. | Corrigir e comprovar limite/espera de retries para impedir repetição que prenda itens. |
| Integridade e histórico | O banco principal passou `integrity_check`, com zero violações de chave estrangeira. As 19.966 identidades do backup histórico aparecem no banco atual, que contém 21.087 itens; 5.480 duplicados também têm registro de arquivamento. | A reconciliação de todos os campos históricos ainda não terminou. |
| Código e entrega | O `HEAD` local coincide com `main` em `333309da`, cujo CI passou. O checkout contém 62 alterações locais que não estão cobertas por esse CI. | Revisar/sincronizar alterações locais e obter CI para a revisão que será entregue. Instalação em outra máquina e operação prolongada continuam sem certificação. |

#### Estado das 15 fases

| Fases | Situação em 28/10/2026 |
| --- | --- |
| 1. Preservação histórica | Integridade e presença das 19.966 identidades confirmadas; reconciliação completa de campos pendente. |
| 2–4. Arquitetura, deduplicação e sete módulos | Implementados; preflight e um fluxo real completos passaram. Descoberta ao vivo e processamento independente nas três fontes não foram certificados em conjunto. |
| 5–6. Python e Bot API | Validados localmente pelo START. |
| 7–8. Organização e portabilidade | Pendentes: 34 arquivos em `runtime/reports`, referências antigas em scripts/exemplos e nenhuma instalação em outro computador. |
| 9. Recovery | Não certificado: 422 repetiu 28 recuperações e 424 retornou a uma falha de IA. |
| 10. Desempenho | Um item usou RVC em CPU e chegou ao Studio; ensaio prolongado de carga no notebook pendente. |
| 11. GitHub e checkout | `HEAD` coincide com `main` em `333309da` e o CI desse commit passou; 62 alterações locais não estão incluídas. |
| 12–13. Integração e START | START passou pelo preflight e um item completou o fluxo; repetição na IA impede certificar operação contínua confiável. |
| 14–15. Documento e entrega | Este registro atualiza a evidência disponível. Auditoria/revisão de legendas, recovery, sincronização das alterações, instalação limpa, operação prolongada e certificação final continuam pendentes. |

Evidências e referências fornecidas para esta atualização: relatório de opções em `storage/validation/published-caption-options-parallel-20261028.md`; commit `333309da85bb6ba301ea8290560e97c97ae9ad6a`; CI `40242044615`. Os totais acima refletem a reavaliação atual informada em 28/10 e não os números de uma captura local anterior do relatório. Nenhuma mensagem Telegram foi modificada durante esta atualização documental.

### Gerador local de legendas — 29/10/2026

O fluxo operacional de IA foi alterado para não instanciar nem chamar Ollama ou Gemini. O `START_ALL.bat` ativa as regras locais; o gerador tenta primeiro fatos e regras determinísticas baseados no contexto persistido pela Vision e valida a legenda pela Policy compartilhada. Quando o registro não contém evidência suficiente, escolhe um fallback neutro curto para permitir que o item continue. A Policy aceita o formato e a evidência privada apenas para a saída exata do compositor local.

| Verificação | Resultado observado |
| --- | --- |
| Replay somente leitura do SQLite operacional | 8.261 itens aprovados pela Vision, com título, e fora de `DUPLICATE` foram processados; distribuição: 8.181 `RECEIVED`, 79 `PUBLISHED` e 1 `RECOVERY`. Os 5.991 duplicados foram excluídos. Nenhum banco foi gravado. |
| Policy e provedores | 8.261/8.261 saídas selecionadas passaram pela Policy; 0 erros e 0 chamadas a provedores externos. |
| Tipo de saída | No replay final, 1.446 saídas combinaram produto e detalhe extraído do contexto no formato das amostras, 460 vieram do compositor factual e 6.355 foram fallback neutro. Os 1.446 casos não foram todos aprovados editorialmente um a um. |
| Categorias/hashtags | 6.509 registros tiveram uma categoria reconhecida pelo vocabulário local; 1.752 continuam sem categoria reconhecida. Títulos sem categoria ou com texto insuficiente continuam sendo uma limitação concreta. |
| Enriquecimento de categoria via Shopee | 325 consultas registradas no orçamento persistente: 315 retornaram `productCatIds`, 9 não encontraram o produto e 1 foi limitada pela API. Os resultados estão no sidecar `work/caption-product-categories.jsonl`; não foram incorporados ao SQLite nem usados no replay. A coleta parou ao receber rate limit. |
| Publicações existentes | A simulação gerou texto diferente para 75 dos 79 registros `PUBLISHED`. Nenhuma mensagem Telegram foi editada nesta verificação. As novas legendas precisam ser apresentadas para revisão antes de qualquer edição. |
| Testes focados | 274 testes de legendas, Policy, integração IA/Coordinator e regressões passaram; 0 falhas. A bateria incluiu exemplos no estilo das legendas listadas pelo usuário e casos de títulos ambíguos. |

O estilo de produto + detalhe reproduz as amostras de referência e os exemplos direcionados passaram pela Policy. No replay final, 6.355 itens ainda recebem fallback neutro; eles não correspondem ao formato específico das amostras. A simulação aponta mudança para 75 das 79 legendas publicadas. Nenhuma mensagem Telegram foi editada. A revisão semântica das novas legendas e a aprovação das publicações continuam pendentes. Este trabalho está apenas no checkout local e ainda não foi sincronizado com o GitHub nem passou pelo CI remoto.

### Certificação operacional — 31/10/2026

Este retrato substitui as contagens operacionais anteriores; os registros datados acima permanecem como histórico. Horário do retrato do SQLite: 08:35, horário de Brasília.

| Verificação | Resultado observado |
| --- | --- |
| Testes locais | 1.065 aprovados, 4 ignorados, 0 falhas; a última regressão isolada de legenda também passou. O checkout continua modificado localmente, portanto esse resultado ainda não corresponde a um commit remoto. |
| START_ALL | Preflight completo aprovado: Python 3.11.9, Speech/RVC, composição dos módulos, três fontes e rotas, credenciais presentes sem exibição e Bot API local pronta. A operação contínua `historico-live-20261025` foi reiniciada e continua ativa. |
| SQLite principal | 21.087 itens: 5.991 `DUPLICATE`, 8.832 `RECEIVED`, 6.170 `WAITING_VISION`, 93 `PUBLISHED` e 1 em `SPEECH`. Os 5.991 duplicados têm referência canônica; não há referências pendentes. |
| Recibos e rotas | 93/93 recibos confirmados, nenhum envio ambíguo. Rota 228: 86; rota 1160: 2; rota 1327: 5; todos no chat `-1004341972306`. |
| Replay das legendas publicadas | O gerador local atual reprocessou 93/93 registros somente para leitura. 93/93 foram aprovados pela Policy, 0 chamadas externas e 0 diferenças entre a legenda persistida e a saída atual. Evidência: `storage/validation/published-caption-replay-20261031.json`. |
| Edição confirmada | A publicação 1415 foi atualizada somente na legenda para `🧡 Calça jeans wide leg` / `#calca`. O próprio gerador local produziu dois candidatos aprovados e selecionou o mais específico; Telegram confirmou a edição, preservando mídia, link, chat e tópico. Relatório: `storage/validation/caption-distinction-20261031-v2.json`. |
| Speech, Studio e Hub reais | O item `-1003788989075_454` concluiu o fluxo e foi confirmado como mensagem 1452 no tópico 228. Speech registrou narração PT-BR com música e decisão RVC elegível. O MP4 publicado foi validado por FFprobe: H.264, AAC estéreo 44,1 kHz, 1080×1920, 10 segundos. |
| Continuidade | A execução foi interrompida com segurança após o item 454 para corrigir a legenda 1415 e reiniciada pelo `START_ALL.bat`; o item 455 retomou o fluxo e está em `SPEECH`. |
| Histórico Vision | As três fontes ainda marcam `historical_complete=0`. Há 6.170 itens aguardando Vision porque não há autorização/orçamento persistente Shopee válido para novas consultas. O programa não contorna esse controle; continua processando os itens já aprovados. |
| GitHub e instalação | `HEAD` local é `333309da85bb6ba301ea8290560e97c97ae9ad6a`, com alterações locais ainda não commitadas. O CI anterior não certifica essas alterações. Instalação limpa em outro computador e sincronização final com GitHub ainda não foram demonstradas. |

O sistema já demonstrou que diferencia e seleciona automaticamente legendas para os exemplos publicados: `Saia com fendas laterais` e `Calça jeans wide leg`. A regra é exercitada por regressão e executada pelo `START_ALL.bat`, sem depender de revisão manual por produto. Isso não torna as legendas sempre únicas: quando o título/Vision não oferecem um detalhe confiável, o fallback factual pode ser mais simples.

A entrega ponta a ponta ainda não deve ser declarada concluída. A operação histórica continua em andamento; a validação de novos produtos pela Shopee aguarda orçamento persistente válido, e o checkout final ainda precisa ser revisado, commitado, sincronizado e aprovado no CI remoto. O snapshot de desempenho observado no item 454 foi de aproximadamente 14 min 52 s desde a entrada em IA até a confirmação; é uma amostra individual, não uma medição prolongada.
