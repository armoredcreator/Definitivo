from __future__ import annotations

import re
import unicodedata
import os
from dataclasses import dataclass
from typing import Any

from .policy import (
    _GENERIC_HASHTAGS,
    _KNOWN_PRODUCT_HEAD_TERMS,
    caption_product_anchor_terms,
    caption_product_category_terms,
)


@dataclass(frozen=True)
class TitleRuleCaption:
    caption: str
    category: str
    hashtag: str
    evidence: tuple[str, ...]

    @property
    def full_caption(self) -> str:
        return f"🧡 {self.caption}\n#{self.hashtag}"


@dataclass(frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    allowed_heads: frozenset[str]
    caption: str
    category: str
    hashtag: str
    evidence: tuple[str, ...]


def _rule(
    pattern: str,
    heads: str,
    caption: str,
    category: str,
    hashtag: str,
    *evidence: str,
) -> _Rule:
    return _Rule(
        re.compile(pattern, re.IGNORECASE),
        frozenset(_fold_word(head) for head in heads.split()),
        caption,
        category,
        hashtag,
        tuple(evidence) or (caption,),
    )


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    # A small subset of catalog exports contains U+FFFD where accented
    # Portuguese characters were decoded incorrectly. Repair only known
    # product-class spellings so those records can still reach a rule.
    text = text.replace("m\ufffdscara", "mascara")
    text = text.replace("cora\ufffd\ufffdo", "coracao")
    text = text.replace("suti\ufffdes", "sutias")
    return "".join(char for char in text if not unicodedata.combining(char))


def _fold_word(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold(value))


def title_rules_enabled() -> bool:
    return os.getenv("ARMORED_IA_CAPTION_TITLE_RULES", "0").strip().casefold() in {
        "1", "true", "yes", "on",
    }


# Rules describe product classes and explicit title details. They intentionally
# do not use publication IDs, shop names, brands, sales copy, or measurements.
_RULES = (
    _rule(r"\bconjunto\b.*\bkimono\b.*\bplus\s+size\b", "kimono conjunto", "Kimono em versão plus size", "kimono", "kimono", "kimono", "plus size"),
    _rule(r"\bdescascador\b.*\bapontador\b", "descascador", "Parece até um apontador", "descascador", "descascador", "apontador"),
    _rule(r"\bcaneta\b.*\bapag[aá]vel\b", "caneta", "A escrita pode ser apagada", "caneta", "caneta", "caneta apagável"),
    _rule(r"\b(regata|blusinha)\b.*\bal[cç]a\s+fina\b", "blusinha blusa regata", "Regata de alça fina", "blusa", "blusinha", "regata alça fina"),
    _rule(r"\bsaia\b(?=[\s\S]*\bfendas?\s+laterais?\b)", "saia", "Saia com fendas laterais", "saia", "saia", "fendas laterais"),
    _rule(r"\bcal[cç]a\b(?=[\s\S]*\bwide\s+leg\b)(?=[\s\S]*\bjeans\b)", "calca", "Calça jeans wide leg", "calca", "calca", "jeans", "wide leg"),
    _rule(r"\bcopo\b.*\bdisplay\s+digital\b", "copo", "Copo com display digital", "copo", "copo", "display digital"),
    _rule(r"\b(smartwatch|rel[oó]gio)\b.*\bilha\s+din[aâ]mica\b", "smartwatch relogio", "Ilha dinâmica no relógio", "smartwatch", "smartwatch", "ilha dinâmica"),
    _rule(r"\bbolsa\b.*\bcompartimento\s+de\s+almo[cç]o\b", "bolsa", "Bolsa com espaço para almoço", "bolsa", "bolsa", "compartimento para almoço"),
    _rule(r"\b(r[aá]dio|autoradio)\b.*\bcarro\b", "radio", "Rádio automotivo", "radio", "radio", "rádio do carro"),
    _rule(r"\bsand[aá]lia\b.*\bde\s+dedo\b", "sandalia", "Tiras entre os dedos", "sandalia", "sandalia", "de dedo"),
    _rule(r"\bbota\b(?=[\s\S]*\bz[ií]per\b)(?=[\s\S]*\bbico\s+fino\b)", "bota", "Zíper e bico fino", "bota", "bota", "zíper bico fino"),
    _rule(r"\bscarpin\b.*\bbico\s+fino\b.*\bsalto\s+alto\b", "scarpin", "Bico fino e salto alto", "scarpin", "scarpin", "bico fino salto alto"),
    _rule(r"\bbota\b.*\bbico\s+fino\b.*\bsalto\s+alto\b", "bota", "Bico fino e salto alto", "bota", "bota", "bico fino salto alto"),
    _rule(r"\bt[eê]nis\b.*\b(treino|esportes)\b", "tenis", "Tênis para acompanhar o treino", "tenis", "tenis", "treino"),
    _rule(r"\bt[eê]nis\b.*\bcasual\b.*\bmacio\b", "tenis", "Tênis casual macio", "tenis", "tenis", "casual macio"),
    _rule(r"\bt[eê]nis\b.*\bcamur[cç]a\b.*\blistra\s+dupla\b", "tenis", "Camurça com listras laterais", "tenis", "tenis", "camurça listra dupla"),
    _rule(r"\bm[aá]scara\b.*\bacidificante\b|\bacidificante\b.*\bm[aá]scara\b", "mascara mascaras", "Máscara acidificante capilar", "mascara", "mascara", "máscara acidificante capilar"),
    _rule(r"\bchinelo\b.*\bver[aã]o\b", "chinelo", "Chinelo para o verão", "chinelo", "chinelo", "chinelo verão"),
    _rule(r"\b(calcinhas?|tanga)\b.*\bsem\s+costura\b", "calcinha calcinhas", "Acabamento sem costura", "calcinha", "calcinha", "sem costura"),
    _rule(r"\besfoliante\b.*\bbanho\b", "esfoliante", "Esfoliação para o banho", "esfoliante", "esfoliante", "esfoliante banho"),
    _rule(r"\bvestido\b.*\bfor(?:r|)o\b.*\bbojo\b", "vestido", "Vestido com forro e bojo", "vestido", "vestido", "forro bojo"),
    _rule(r"\bponcho\b.*\btricot?\b.*\bgola\s+alta\b", "poncho", "Tricô com gola alta", "poncho", "poncho", "tricô gola alta"),
    _rule(r"\bsuti[aã]s?\b.*\bmicrofibra\b.*\bbojo\b", "sutia sutias", "Microfibra com bojo", "sutia", "sutia", "microfibra bojo"),
    _rule(r"\bmoletom\b.*\b(interna|interno)\b.*\bpel[uú]cia\b", "moletom", "Interior com pelúcia", "moletom", "moletom", "pelúcia interna"),
    _rule(r"\bvestido\b.*\btropical\b.*\bestampado\s+floral\b", "vestido", "Estampa floral tropical", "vestido", "vestido", "tropical estampado floral"),
    _rule(r"\bcachecol\b.*\blongo\b.*\bxadrez\b", "lenco", "Cachecol longo em xadrez", "lenco", "lenco", "cachecol longo xadrez"),
    _rule(r"\b(cachecol|pashmina|pashimina)\b", "lenco", "Cachecol para o inverno", "lenco", "lenco", "cachecol inverno"),
    _rule(r"\bpijama\b.*\bmanga\s+longa\b", "pijama", "Pijama de manga longa", "pijama", "pijama", "manga longa"),
    _rule(r"\bbandeja\b.*\bpinc[eé]is\b", "pinceis", "Bandeja para pincéis", "pinceis", "pinceis", "bandeja pincéis"),
    _rule(r"\bblusa\b.*\bestampa\s+on[cç]a\b", "blusa", "Estampa de onça", "blusa", "blusa", "estampa onça"),
    _rule(r"\bsand[aá]lia\b.*\bplataforma\b", "sandalia", "Sandália com plataforma", "sandalia", "sandalia", "sandália plataforma"),
    _rule(r"\bgel\s+de\s+limpeza\b.*\bsuave\b", "gel skincare", "Gel de limpeza suave", "gel", "gel", "gel limpeza suave"),
    _rule(r"\bbota\b.*\bz[ií]per\b.*\bbico\s+fino\b", "bota", "Zíper e bico fino", "bota", "bota", "zíper bico fino"),
    _rule(r"\bm[aá]scara\s+labial\b.*\bcol[aá]geno\b", "mascara mascaras", "Colágeno para os lábios", "mascara", "mascara", "máscara labial colágeno"),
    _rule(r"\b(gel\s+pads|adesivo)\b.*\bolheiras\b|\bolheiras\b.*\bgel\s+pads\b", "mascara mascaras", "Gel para olheiras", "mascara", "mascara", "gel pads olheiras"),
    _rule(r"\bpingente\b.*\bcora[cç][aã]o\b", "colar colares", "Pingente em forma de coração", "colar", "colar", "pingente coração"),
    _rule(r"\bcolar\b.*\bcora[cç][aã]o\s+liso\b", "colar colares", "Pingente de coração liso", "colar", "colar", "coração liso"),
    _rule(r"\bsapatilha\b.*\bbico\s+fino\b.*\bcord[aã]o\s+tran[cç]ado\b", "sapatilha", "Bico fino com cordão trançado", "sapatilha", "sapatilha", "bico fino cordão trançado"),
    _rule(r"\bblusa\b.*\bgola\s+alta\b.*\blistrada\b", "blusa", "Gola alta com listras", "blusa", "blusa", "gola alta listrada"),
    _rule(r"\bblusa\b.*\bcerejinhas\b", "blusa", "Estampa de cerejinhas", "blusa", "blusa", "estampa cerejinhas"),
    _rule(r"\bcalcinhas\b.*\balgod[aã]o\b", "calcinha calcinhas", "Calcinhas de algodão", "calcinha", "calcinha", "calcinhas algodão"),
    _rule(r"\bblusa\b.*\bmanga\s+longa\b", "blusa", "Blusa de manga longa", "blusa", "blusa", "manga longa"),
    _rule(r"\bbota\b.*\bbico\s+fino\b.*\bcano\s+m[eé]dio\b", "bota", "Bico fino e cano médio", "bota", "bota", "bico fino cano médio"),
    _rule(r"\bbota\b.*\bcano\s+alto\b.*\bfivelas\b", "bota", "Bota de cano alto", "bota", "bota", "cano alto fivelas"),
    _rule(r"\bbrincos?\b.*\bgeom[eé]tric[oa]\b.*\bcora[cç][aã]o\b", "brinco brincos", "Brincos geométricos com coração", "brinco", "brinco", "geométrico coração"),
    _rule(r"\bshampoo\b.*\bcondicionador\b", "shampoo", "Shampoo e condicionador", "shampoo", "shampoo", "shampoo condicionador"),
    _rule(r"\bblusa\b.*\btran.{0,2}a\b.*\btricot\b|\bblusa\b.*\btricot\b.*\btran.{0,2}a\b", "blusa", "Tranças no tricô", "blusa", "blusa", "trança tricô"),
    _rule(r"\bcolete\b.*\btricot\b.*\btran.{0,2}as?\b", "colete", "Colete trançado de tricô", "colete", "colete", "colete tricô tranças"),
    _rule(r"\b(cachecol|pashmina|pashimina)\b", "lenco", "Cachecol para o inverno", "lenco", "lenco", "cachecol inverno"),
    _rule(r"\bcamiseta\b.*\bestampada\b.*\balgod[aã]o\b", "camiseta", "Camiseta estampada de algodão", "camiseta", "camiseta", "camiseta estampada algodão"),
    _rule(r"\b(?:t-?shirt|camiseta|blusa)\b(?=[\s\S]*\b\d+\s+estampas?\b)", "tshirt camiseta blusa", "Estampas variadas", "tshirt", "tshirt", "estampas variadas"),
    _rule(r"\bmeia\s+soquete\b.*\balgod[aã]o\b", "meia", "Meias soquete de algodão", "meia", "meia", "meia soquete algodão"),
    _rule(r"\bcachecol\b.*\blongo\b.*\bxadrez\b", "lenco", "Cachecol longo em xadrez", "lenco", "lenco", "cachecol longo xadrez"),
    _rule(r"\bcardigan\b.*\bxadrez\b", "casaco cardigan", "Cardigan xadrez de tricô", "cardigan", "cardigan", "cardigan xadrez tricô"),
    _rule(r"\bsabonete\b.*\bcreme\b.*\bfacial\b", "sabonete", "Sabonete e creme facial", "sabonete", "sabonete", "sabonete creme facial"),
    _rule(r"\bt[eê]nis\b.*\bplataforma\s+alta\b", "tenis", "Tênis com plataforma alta", "tenis", "tenis", "tênis plataforma alta"),
    _rule(r"\bmoletom\b.*\bcanguru\b", "moletom", "Bolso canguru no moletom", "moletom", "moletom", "moletom canguru"),
    _rule(r"\bcardigan\b.*\baberto\b.*\btric[oô]\b", "casaco cardigan", "Cardigan aberto de tricô", "cardigan", "cardigan", "cardigan aberto tricô"),
    _rule(r"\bcoturno\b.*\bcanelada\b.*\bmeia\b", "bota", "Coturno canelado com meia", "bota", "bota", "coturno canelado meia"),
    _rule(r"\bmoletom\b.*\b100%\s+algod[aã]o\b", "moletom", "Moletom de algodão", "moletom", "moletom", "moletom algodão"),
    _rule(r"\brelogio\b.*\bled\b.*\bdigital\b", "relogio", "Relógio LED digital", "relogio", "relogio", "relógio led digital"),
    _rule(r"\bcal[cç]a\b.*\bpantalona\b.*\bcintura\s+alta\b", "calca", "Calça pantalona de cintura alta", "calca", "calca", "pantalona cintura alta"),
    _rule(r"\b[oó]culos\s+de\s+sol\b.*\bquadrado\b", "oculos", "Óculos de armação quadrada", "oculos", "oculos", "óculos quadrado"),
    _rule(r"\bkit\b.*\bsos\s+crescimento\b.*\bhair\b", "", "Kit de cuidado capilar", "cabelo", "cabelo", "cuidado capilar crescimento hair"),
    _rule(r"\bcal[cç]a\s+jeans\b.*\bwide\s+leg\b", "calca jeans", "Jeans de cintura alta", "jeans", "jeans", "jeans wide leg cintura alta"),
    _rule(r"\btouca\b.*\bcetim\b.*\bdupla\s+camada\b", "touca", "Touca dupla de cetim", "touca", "touca", "touca cetim dupla camada"),
    _rule(r"\bsobretudo\b.*\bl[aã]\b", "casaco", "Sobretudo de lã", "casaco", "casaco", "sobretudo lã"),
    _rule(r"\b[oó]leo\b.*\breparador\s+de\s+pontas\b", "oleo", "Óleo reparador de pontas", "oleo", "oleo", "óleo reparador pontas"),
    _rule(r"\bpapete\b.*\bstrass\b", "sandalia", "Strass na papete", "sandalia", "sandalia", "papete strass"),
    _rule(r"\bmochila\b.*\b(?:[aà]\s+prova\s+d['’]?\s?[aá]gua|prova\s+d['’]?\s?[aá]gua)\b", "mochila", "Mochila à prova d’água", "mochila", "mochila", "mochila à prova d’água"),
    _rule(r"\bcal[cç]a\b.*\bpantalona\b.*\bc[oó]s\s+duplo\b.*\bel[aá]stico\b", "calca", "Calça pantalona com cós elástico", "calca", "calca", "pantalona cós duplo elástico"),
    _rule(r"\bpantufa\b.*\bcano\s+longo\b", "pantufa", "Pantufa com cano longo", "pantufa", "pantufa", "pantufa cano longo"),
    _rule(r"\bcintos\b.*\bfivela\b.*\bdourada\b", "cintos cinto", "Cintos com fivelas douradas", "cinto", "cinto", "cintos fivela dourada"),
    _rule(r"\bvestido\b.*\bmanga\s+longa\b", "vestido", "Vestido de manga longa", "vestido", "vestido", "vestido manga longa"),
    _rule(r"\bvestido\b.*\bbabado\b.*\bmanga\s+bufante\b", "vestido", "Babados e mangas bufantes", "vestido", "vestido", "babado manga bufante"),
    _rule(r"\bbody\s+splash\b", "body", "Fragrância para o corpo", "body", "body", "body splash"),
    _rule(r"\bsuti[aã]s?\b.*\b(?:renda.*bojo|bojo.*renda)\b", "sutia sutias", "Renda com bojo", "sutia", "sutia", "renda bojo"),
    _rule(r"\bconjunto\b.*\bpo[aá]\b.*\balfaiataria\b", "colete conjunto", "Conjunto de alfaiataria poá", "conjunto", "conjunto", "conjunto poá alfaiataria"),
    _rule(r"\b[oó]leo\b.*\b3\s+em\s+1\b", "oleo", "Óleo multifuncional", "oleo", "oleo", "óleo 3 em 1"),
    _rule(r"\bvestido\b.*\bacinturado\b", "vestido", "Vestido de modelagem acinturada", "vestido", "vestido", "vestido acinturado"),
    _rule(r"\btamanco\b.*\bsalto\s+bloco\b", "tamanco", "Tamanco de salto bloco", "tamanco", "tamanco", "tamanco salto bloco"),
    _rule(r"\bbody\b.*\bmula\s+manca\b", "body", "Body de um ombro só", "body", "body", "body mula manca"),
    _rule(r"\bacess[oó]rios\b.*\bskincare\b", "skincare", "Acessórios para skincare", "skincare", "skincare", "acessórios skincare"),
    _rule(r"\bprotetor\s+t[eé]rmico\b.*\bcabelo\b", "protetor", "Proteção térmica para cabelo", "protetor", "protetor", "protetor térmico cabelo"),
    _rule(r"\badesivo\b.*\bantiderrapante\b.*\b(?:sola|solado)\b", "adesivo", "Adesivo antiderrapante para o solado", "adesivo", "adesivo", "adesivo antiderrapante sola sapato"),
    _rule(r"\bx[ií]caras\b.*\bch[aá]\b.*\bcaf[eé]\b", "xicaras", "Xícaras para chá e café", "xicaras", "xicaras", "xícaras chá café"),
    _rule(r"\bpulseira\b.*\bajust[aá]vel\b.*\bdourada\b", "pulseira", "Pulseira ajustável dourada", "pulseira", "pulseira", "pulseira ajustável dourada"),
    # Reusable catalog classes that appeared in the historical replay but
    # were not covered by the first-pass title vocabulary.
    _rule(r"\b(?:conjunto|jogo)\s+de\s+jantar\b", "", "Louças para jantar", "loucas", "loucas", "conjunto de jantar"),
    _rule(r"\b(?:conjunto|suprimentos?)\b.*\bartesanato\b", "", "Kit para artesanato", "artesanato", "artesanato", "artesanato"),
    _rule(r"\bcentral\s+multim[ií]dia\b.*\b(?:2\s*din|android|gps)\b", "", "Central multimídia para carro", "radio", "radio", "central multimídia", "2 din"),
    _rule(r"\bcobre\s+leito\b.*\bdupla\s+face\b", "", "Cobre-leito dupla face", "cobreleito", "cobreleito", "cobre-leito", "dupla face"),
    _rule(r"\bcleansing\s+oil\b", "", "Óleo de limpeza facial", "oleo", "oleo", "cleansing oil"),
    _rule(r"\bpegador\b.*\besp[aá]tula\b|\besp[aá]tula\b.*\bpegador\b", "", "Espátula para a cozinha", "espatula", "espatula", "espátula", "cozinha"),
    _rule(r"\bpente\b.*\bpiolh", "", "Pente para piolhos", "pente", "pente", "pente", "piolhos"),
    _rule(r"\bfecha\s+embalagem\b.*\b(?:pacote|sucrilhos)\b", "", "Fecho para pacotes", "fecho", "fecho", "fecha embalagem", "pacote"),
    _rule(r"\bporta\s+mantimento\b", "", "Pote para mantimentos", "pote", "pote", "porta mantimento"),
    _rule(r"\bbalan[cç]o\s+suspenso\b.*\bportas?\b", "", "Balanço para porta", "balanco", "balanco", "balanço suspenso", "porta"),
    _rule(r"\bpula\s+pula\b.*\binfantil\b", "", "Pula-pula infantil", "brinquedo", "brinquedo", "pula pula", "infantil"),
    _rule(r"\bmarca\s*[- ]?texto\b.*\bestampad[oa]\b", "", "Marca-texto estampado", "marcatexto", "papelaria", "marca-texto", "estampado"),
    _rule(r"\butens[ií]lios?\s+de\s+cozinha\b", "", "Utensílios para cozinha", "utensilios", "cozinha", "utensílios", "cozinha"),
    _rule(r"\bsacos?\s+pl[aá]sticos?\b.*\bfreezer\b", "", "Sacos para freezer", "saco", "saco", "sacos plásticos", "freezer"),
    _rule(r"\bconjunto\s+infantil\b.*\bmenina\b.*\bver[aã]o\b", "", "Conjunto infantil de verão", "conjunto", "moda", "conjunto infantil", "verão"),
    _rule(r"\b(?:cosplay|fantasia)\b.*\b(?:c[aã]o|gato|pet|animais?)\b", "", "Fantasia para pets", "fantasia", "fantasia", "fantasia", "cão"),
    _rule(r"\blip\s+balm\b", "", "Balm para os lábios", "balm", "beleza", "lip balm"),
    _rule(r"\bconjunto\b.*\bfondue\b", "", "Conjunto para fondue", "fondue", "fondue", "conjunto", "fondue"),
    _rule(r"\baction\s+figure\b", "", "Figura de ação", "figura", "figura", "action figure"),
    _rule(r"\b(?:bb\s*cream|perfect\s+cover)\b", "", "BB cream para a pele", "base", "maquiagem", "BB Cream"),
    _rule(r"\bporta[- ]chaves?\b.*\bgaragem\b", "", "Chaveiro para garagem", "chaveiro", "chaveiro", "porta-chaves", "garagem"),
    _rule(r"\bjesus\b.*\bpel[uú]cia\b.*\bm[uú]sica\b", "", "Pelúcia com música", "pelucia", "pelucia", "pelúcia", "música"),
    _rule(r"\bquebra[- ]cabe[cç]a\b.*\banimais\b", "", "Quebra-cabeça de animais", "quebracabeca", "brinquedo", "quebra-cabeça", "animais"),
    _rule(r"\blava\s+lou[cç]as?\b.*\bport[aá]til\b", "", "Lava-louças portátil", "lavaloucas", "lavaloucas", "lava-louças", "portátil"),
    _rule(r"\bcabides?\b.*\bmultiuso\b", "", "Cabides multiuso", "cabide", "cabide", "cabides", "multiuso"),
    _rule(r"\blava\s+roupas?\b.*\bl[ií]quido\b", "", "Lava-roupas líquido", "detergente", "detergente", "lava roupas", "líquido"),
    _rule(r"\bflamingo\b.*\b(?:ta[cç]a|goblet|glass)\b|\b(?:ta[cç]a|goblet|glass)\b.*\bflamingo\b", "", "Taça em forma de flamingo", "taca", "taca", "taça", "flamingo"),
    _rule(r"\bflor\b.*\b(?:fio de fada|foto personalizada)\b", "", "Flor com fio de luzes", "flor", "flor", "flor", "fio de fada"),
    _rule(r"\b(?:roupas?|traje)\b.*\b(?:c[aã]es?|cachorro|animais?)\b.*\b(?:abelh[ao]|abelha)\b", "", "Fantasia de abelha para cães", "fantasia", "fantasia", "roupa para cães", "abelha"),
    _rule(r"\bbiber[aã]o\b|\bbiber[aã]o\b", "", "Mamadeira para bebê", "mamadeira", "mamadeira", "biberão", "leite materno"),
    _rule(r"\bgrampos?\b.*\bcabelo\b.*\bflor", "", "Grampos florais para cabelo", "grampo", "grampo", "grampos", "cabelo", "flor"),
    _rule(r"\bmini\s+est[uú]dio\s+de\s+cer[aâ]mica\b", "", "Cerâmica para criar", "artesanato", "artesanato", "estúdio de cerâmica"),
    _rule(r"\bconjunto\b.*\bplus\s+size\b", "conjunto", "Conjunto plus size", "conjunto", "moda", "conjunto", "plus size"),
    _rule(r"\bconjunto\b.*\bfeminino\b", "conjunto", "Conjunto feminino", "conjunto", "moda", "conjunto", "feminino"),
    _rule(r"\btop\b.*\bacademia\b.*\bfitness\b", "", "Top para academia", "top", "moda", "top", "academia"),
    _rule(r"\b(?:baile|enfeites?)\b.*\b(?:natal|christmas)\b", "", "Enfeites natalinos", "enfeite", "natal", "enfeite", "Natal"),
    _rule(r"\bpapai\s+noel\b.*\b(?:decora[cç][aã]o|musical)\b", "", "Papai Noel musical", "decoracao", "natal", "Papai Noel", "musical"),
    _rule(r"\bcampainha\b.*\bsem\s+fio\b", "", "Campainha sem fio", "campainha", "campainha", "campainha", "sem fio"),
    _rule(r"\bmini\s+grill\b.*\bel[eé]trico\b", "", "Grill elétrico compacto", "grill", "grill", "grill elétrico"),
    _rule(r"\bpel[uú]cia\b.*\binterativa\b", "", "Pelúcia interativa", "pelucia", "pelucia", "pelúcia", "interativa"),
    _rule(r"\bcueiro\b.*\bbeb[eê]\b", "", "Cueiro para bebê", "cueiro", "cueiro", "cueiro", "bebê"),
    _rule(r"\bkit\b.*\b(?:3|03)\b.*\bcabide\b", "", "Cabides para organizar", "cabide", "cabide", "cabide", "kit"),
    _rule(r"\bca[cç]arola\b.*\b(?:indu[cç][aã]o|cer[aâ]mica)\b", "", "Caçarola para indução", "cacarola", "cacarola", "caçarola", "indução"),
    _rule(r"\bconjunto\s+de\s+assadeiras?\b.*\bvidro\b", "", "Assadeiras de vidro", "assadeira", "assadeira", "assadeiras", "vidro"),
    _rule(r"\bporta[- ]temperos\b.*\bacr[ií]lico\b", "", "Porta-temperos de acrílico", "temperos", "temperos", "porta-temperos", "acrílico"),
    _rule(r"\bporta[- ]panetone\b", "", "Porta-panetone para o Natal", "panetone", "panetone", "porta-panetone"),
    _rule(r"\btoalha[s]?\b.*\bb(?:anh[aã]o|anho)\b", "", "Toalhas de banho", "toalha", "toalha", "toalhas", "banhão"),
    # Reusable title structures found in the read-only replay of Vision data.
    # Captions keep product facts while omitting seller brands, model codes,
    # measurements, and promotional wording.
    _rule(r"\bperfume\b.*\b[oó]leo\b.*\b[aá]rabe\b", "", "Perfume em óleo árabe", "perfume", "perfume", "perfume", "óleo árabe"),
    _rule(r"\bespelho\b.*\bmaquiagem\b.*\bdobr[aá]vel\b|\bespelho\b.*\bdobr[aá]vel\b.*\bmaquiagem\b", "", "Espelho dobrável para maquiagem", "espelho", "espelho", "espelho", "dobrável", "maquiagem"),
    _rule(r"\btintura\b.*\bcabelo\b.*\bcores?\b", "", "Tintura para cabelo em várias cores", "tintura", "cabelo", "tintura", "cabelo", "cores"),
    _rule(r"\bcamiseta\b.*\bbrasil\b", "", "Camiseta do Brasil", "camiseta", "camiseta", "Brasil"),
    _rule(r"\b(?:adesivo|pastilha|gel)\b.*\b(?:sanit[aá]rio|vaso|banheiro)\b", "", "Pastilha perfumada para o banheiro", "pastilha", "banheiro", "pastilha", "sanitário"),
    _rule(r"\b(?:banda|pulseira)s?\b.*\b(?:apple\s+watch|rel[oó]gio)\b.*\b(?:metal|a[cç]o)", "", "Pulseira de metal para relógio", "pulseira", "pulseira", "pulseira", "metal"),
    _rule(r"\bprotetores?\s+solares?\b.*\bfaciais?\b|\bprotetores?\b.*\bsolar(?:es)?\b.*\bfacial", "", "Protetor solar facial", "protetor", "protetor", "protetor solar", "facial"),
    _rule(r"\bcontrole\b.*\bsem\s+fio\b.*\b(?:console|pc|gamepad)", "", "Controle sem fio para jogos", "controle", "controle", "sem fio", "console"),
    _rule(r"\bestrela\s+do\s+mar\b.*\bporta[- ]?joias\b", "", "Estrela decorativa de concreto", "estrela", "decoracao", "estrela do mar", "concreto"),
    _rule(r"\baspirador\b.*\bport[aá]til\b.*\b(?:luz|led)\b", "", "Aspirador portátil com LED", "aspirador", "aspirador", "portátil", "LED"),
    _rule(r"\bescorredor\b.*\bsuspenso\b.*\b(?:lou[cç]as|cozinha)", "", "Escorredor suspenso para louças", "escorredor", "escorredor", "suspenso", "louças"),
    _rule(r"\bdescascador\b.*\breservat[oó]rio\b", "descascador", "Descascador com reservatório", "descascador", "descascador", "reservatório"),
    _rule(r"\bcaneca\b.*\b(?:frases?|desenhos?|memes?)\b", "caneca", "Caneca com frases e desenhos", "caneca", "caneca", "frases", "desenhos"),
    _rule(r"\bsmartwatch\b.*\b(?:galaxy|watch\d|venu)\b", "smartwatch", "Smartwatch no cotidiano", "smartwatch", "smartwatch", "smartwatch"),
    _rule(r"\bcaf[eé]\b.*\bar[aá]bica\b", "cafe", "Café arábica", "cafe", "cafe", "café", "arábica"),
    _rule(r"\b(?:jogo|kit)\b.*\bsoquetes?\b.*\bchaves?\b|\bsoquetes?\b.*\bchaves?\b.*\bcatraca\b", "", "Jogo de soquetes e chaves", "soquete", "soquete", "soquetes", "chaves"),
    _rule(r"\bkit\b.*\bsabonete\b.*\bhidratante\b.*\besfoliante\b", "", "Cuidados para corpo e rosto", "kit", "beleza", "sabonete", "hidratante", "esfoliante", "corpo e rosto"),
    _rule(r"\bdelineador\b.*\bcarimbo\b", "delineador", "Delineado com carimbo", "delineador", "delineador", "carimbo"),
    _rule(r"\b(?:[aá]rvore|[aá]rvores)\b.*\b(?:papel|cristal|cerejeira|sakura)\b", "arvore", "Árvore decorativa em papel", "arvore", "arvore", "árvore", "papel"),
    _rule(r"\bspray\b.*\bsecante\b.*\besmalte", "spray", "Spray secante para esmaltes", "spray", "esmalte", "spray secante", "esmaltes"),
    _rule(r"\btinta\b.*\besmalte\b.*\bferrugem\b", "tinta", "Tinta esmalte para ferrugem", "tinta", "tinta", "esmalte", "ferrugem"),
    _rule(r"\bjaqueta\b.*\bbomber\b.*\bcour[ií]no\b", "jaqueta", "Jaqueta bomber em courino", "jaqueta", "jaqueta", "bomber", "courino"),
    _rule(r"\b(?:box|cole[cç][aã]o)\b.*\b(?:biblioteca|livrinhos?)\b", "", "Box de livrinhos", "livro", "livro", "box", "livrinhos"),
    _rule(r"\bforma\b.*\b(?:sorvete|picol[eé])\b", "forma", "Forma para picolé", "forma", "forma", "picolé"),
    _rule(r"\bsof[aá]\b(?=[\s\S]*\b(?:gatos?|c[aã]es?|cachorros?|pets?)\b)(?=[\s\S]*\bpel[uú]cia\b)", "sofa", "Caminha de pelúcia para pets", "caminha", "pet", "sofá", "pelúcia", "pet"),
    _rule(r"\bc[aã]o\s+rob[oó]\b.*\b(?:controle\s+remoto|rc)\b", "", "Cão robô de controle remoto", "robo", "robo", "cão robô", "controle remoto"),
    _rule(r"\bbichinho\s+virtual\b", "bichinho", "Bichinho virtual", "bichinho", "bichinho", "bichinho virtual"),
    _rule(r"\bcortina\b.*\b(?:voil|linho)\b.*\bsu[ií]co\b", "cortina", "Cortina de voil e linho", "cortina", "cortina", "voil", "linho"),
    _rule(r"\b(?:gear\s+cube|cubo\s+m[aá]gico)\b.*\b(?:gear|engrenagem)", "cubo", "Cubo mágico com engrenagens", "cubo", "cubo", "gear cube", "engrenagens"),
    _rule(r"\bumidificador\b.*\bvulc[aã]o\b", "umidificador", "Umidificador em formato de vulcão", "umidificador", "umidificador", "vulcão"),
    _rule(r"\bjogo\b.*\btigelas\b", "tigela tigelas", "Jogo de tigelas", "tigela", "tigela", "jogo", "tigelas"),
    _rule(r"\bmoletom\b.*\bz[ií]per\b", "moletom", "Moletom com zíper", "moletom", "moletom", "zíper"),
    _rule(r"\bcaneta\b.*\b(?:caligrafia|cursiva)\b.*\b(?:escreva|apague)", "caneta", "Caneta para caligrafia", "caneta", "caneta", "caligrafia", "cursiva"),
    _rule(r"\bsuporte\b.*\bescova\b.*\bpasta\s+de\s+dentes\b", "suporte", "Suporte de escova e pasta", "suporte", "suporte", "escova", "pasta de dentes"),
    _rule(r"\bcanetas?\b.*\b(?:coloridas?|cores?)\b.*\bponta\s+fina\b|\bcanetas?\b.*\bponta\s+fina\b.*\b(?:coloridas?|cores?)\b", "caneta canetas", "Canetas de ponta fina", "caneta", "caneta", "ponta fina", "coloridas"),
    _rule(r"\bpista\b.*\b(?:hot\s+wheels|carrinhos?)\b|\bhot\s+wheels\b.*\bpista\b", "pista", "Pista para carrinhos", "pista", "pista", "carrinhos"),
    _rule(r"\b(?:top|cropped)\b.*\b(?:alfaiataria|corset)\b", "top cropped", "Cropped de alfaiataria", "cropped", "cropped", "alfaiataria"),
    _rule(r"\bconjunto\b.*\bcamisa\b.*\bshort\b.*\blinho\b|\bconjunto\b.*\blinho\b.*\bcamisa\b", "", "Conjunto de linho", "conjunto", "moda", "conjunto", "linho"),
    _rule(r"\bartesanato\b.*\bconjunto\b|\bconjunto\b.*\bartesanato\b", "", "Kit para artesanato", "artesanato", "artesanato", "artesanato"),
    _rule(r"\bpuff\b.*\btecido\b", "puff", "Puff de tecido", "puff", "puff", "tecido"),
    _rule(r"\bralador\b.*\bfatiador\b.*\b(?:legumes|queijo|vegetais)\b", "ralador fatiador", "Ralador e fatiador manual", "ralador", "ralador", "ralador", "fatiador"),
    _rule(r"\bsapateira\b.*\bportas?\b", "sapateira", "Sapateira com portas", "sapateira", "sapateira", "sapateira", "portas"),
    _rule(r"\bpoltrona[- ]cama\b|\bpoltrona\b.*\bcama\b", "poltrona", "Poltrona que vira cama", "poltrona", "poltrona", "poltrona", "cama"),
    _rule(r"\bmop\b.*\bbalde\b.*\bcabo\b", "mop", "Mop com balde e cabo", "mop", "mop", "balde", "cabo"),
    _rule(r"\bpisca[- ]?pisca\b.*\b(?:natal|[aá]rvore)", "pisca", "Pisca-pisca para o Natal", "pisca", "natal", "pisca-pisca", "Natal"),
    _rule(r"\b(?:ar[- ]condicionado|climatizador|ventilador)\b(?=[\s\S]*\b(?:[aá]gua|gelo)\b)(?=[\s\S]*\b(?:umidificador|led)\b)", "", "Ventilador com água e gelo", "ventilador", "ventilador", "água", "gelo"),
    _rule(r"\b(?:electric\s+)?massager\b.*\b(?:muscle|muscular)", "massager", "Massageador muscular", "massageador", "massageador", "muscle"),
    _rule(r"\b(?:cascata|cortina)\b.*\b(?:natal|led)\b.*\b(?:bolas|decora[cç][aã]o)", "", "Cortina de luzes natalina", "cortina", "natal", "cortina", "LED", "Natal"),
    _rule(r"\bgarrafas?\b.*\b(?:[aá]gua|jarra)\b", "garrafa garrafas", "Garrafa para água", "garrafa", "garrafa", "garrafa", "água"),
    _rule(r"\b(?:limpa[- ]forno|limpa\s+forno)\b|\bspray\b.*\bforno\b", "", "Spray limpa-forno", "limpeza", "limpeza", "forno", "spray"),
    _rule(r"\bboleira\b.*\b(?:bandejas?|doceiras?)\b.*\bfesta\b", "boleira", "Boleira e bandejas para festa", "boleira", "boleira", "boleira", "bandejas", "festa"),
    _rule(r"\btela\b(?=[\s\S]*\b(?:projetor|proje[cç][aã]o|tel[aã]o)\b)(?=[\s\S]*\btransl[uú]cida\b)", "", "Telão translúcido para projetor", "telao", "telao", "translúcido", "projetor"),
    _rule(r"\bpanelas?\b.*\b(?:revestimento\s+cer[aâ]mico|cer[aâ]mica)\b.*\bindu[cç][aã]o\b", "panela panelas", "Panelas para indução", "panela", "panela", "cerâmica", "indução"),
    _rule(r"\bprateleira\b.*\bbambu\b", "prateleira", "Prateleira de bambu", "prateleira", "prateleira", "bambu"),
    _rule(r"\bt[aá]bua\b.*\b(?:petiscos|bambu)\b", "tabua", "Tábua de petiscos de bambu", "tabua", "tabua", "petiscos", "bambu"),
    _rule(r"\bcabideiro\b.*\b(?:ganchos?|cabides?)\b", "cabideiro", "Cabideiro com ganchos", "cabideiro", "cabideiro", "ganchos"),
    _rule(r"\bpapel\s+adesivo\b.*\bparede\b.*\blinho\b", "papel", "Papel de parede efeito linho", "papel", "papel", "adesivo", "parede", "linho"),
    _rule(r"\bfidget\s+spinner\b.*\b(?:transformer|mec[aâ]nic[ao])", "spinner", "Spinner mecânico", "spinner", "spinner", "mecânico"),
    _rule(r"\b(?:lumin[aá]ria|armadilha)\b.*\b(?:mosquitos?|insetos?)\b", "luminaria", "Luminária contra mosquitos", "luminaria", "luminaria", "mosquitos"),
    _rule(r"\b(?:inflador|bomba)\s+el[eé]tric[ao]\b.*\b(?:bal[aã]o|bexiga)s?\b", "", "Bomba elétrica para balões", "bomba", "bomba", "balões", "elétrica"),
    _rule(r"\bsaquinhos?\b.*\bcubos?\s+de\s+gelo\b", "saco saquinho", "Saquinhos para cubos de gelo", "saco", "saco", "saquinhos", "gelo"),
    _rule(r"\btratamento\s+capilar\b.*\b(?:col[aá]geno|collagen)\b", "", "Tratamento capilar com colágeno", "tratamento", "cabelo", "capilar", "colágeno"),
    _rule(r"\b(?:colageno|collagen)\b.*\btratamento\s+capilar\b", "", "Tratamento capilar com colágeno", "tratamento", "cabelo", "capilar", "collagen"),
    _rule(r"\bcarrinho\b.*\bcole[cç][aã]o\b.*\b(?:ferro|metal)\b", "carrinho", "Carrinho de coleção", "carrinho", "carrinho", "coleção"),
    _rule(r"\bring\s+light\b.*\btrip[eé]\b", "", "Ring light com tripé", "ringlight", "ringlight", "tripé"),
    _rule(r"\bchave\b.*\bsoquete\b.*\bmultifuncional\b", "chave", "Chave soquete multifuncional", "chave", "chave", "soquete", "multifuncional"),
    _rule(r"\bsilicone\b.*\b(?:rugas|rosto|pesco[cç]o)\b.*\b(?:adesivo|reutiliz[aá]vel)", "silicone adesivo", "Adesivo de silicone para pele", "adesivo", "pele", "silicone", "pele"),
    _rule(r"\bprojetor\b.*\b(?:luzes|padr[oõ]es|natal)\b", "projetor", "Projetor de luzes natalinas", "projetor", "natal", "projetor", "luzes", "Natal"),
    _rule(r"\b(?:bolsa|sacola)\b.*\bdobr[aá]vel\b.*\brodinhas\b", "bolsa sacola", "Bolsa dobrável com rodinhas", "bolsa", "bolsa", "dobrável", "rodinhas"),
    _rule(r"\b(?:fluido|l[ií]quido)\b.*\b(?:hourglass|ampulheta)\b.*\bdecor", "", "Ampulheta líquida decorativa", "ampulheta", "ampulheta", "líquida", "decorativa"),
    _rule(r"\b(?:mousse|espuma)\b.*\bdepilat[oó]ri[ao]\b", "mousse espuma", "Mousse depilatória", "mousse", "mousse", "depilatória"),
    _rule(r"\b(?:calcinha|short|boxer)\b.*\b(?:box|shortinho|segunda\s+pele)\b", "calcinha short shorts", "Calcinha estilo short", "calcinha", "calcinha", "short", "segunda pele"),
    _rule(r"\blumin[aá]ria\b.*\b(?:magn[eé]tica|flutuante)\b.*\b(?:led|l[aâ]mpada)\b", "luminaria", "Luminária magnética flutuante", "luminaria", "luminaria", "magnética", "flutuante"),
    _rule(r"\bplacas?\b.*\b(?:piso|parede)\b.*\bautocolante\b", "", "Placas para piso e parede", "placa", "placa", "placas", "piso", "parede"),
    _rule(r"\b(?:gimbal|suporte)\b.*\brastreamento\b.*\b(?:rosto|telefone|celular)\b", "", "Suporte de celular com rastreamento", "suporte", "suporte", "rastreamento", "celular"),
    _rule(r"\b(?:suporte|caixa)\b.*\b(?:papel\s+toalha|porta[- ]papel)\b.*\bcelular\b", "", "Suporte para celular e papel-toalha", "suporte", "suporte", "celular", "papel-toalha"),
    _rule(r"\bjogo\s+de\s+mesa\b.*\bfutebol\b", "", "Futebol de mesa", "futebol", "futebol", "jogo de mesa", "futebol"),
    _rule(r"\btintura\b(?=[\s\S]*\bcabelo\b)(?=[\s\S]*\bcores?\b)", "", "Tintura de cabelo colorida", "tintura", "cabelo", "tintura", "cabelo", "cores"),
    _rule(r"\bescorredor\b(?=[\s\S]*\bsuspenso\b)(?=[\s\S]*\b(?:lou[cç]as|cozinha)\b)", "", "Escorredor suspenso com porta", "escorredor", "escorredor", "suspenso", "porta"),
    _rule(r"\bcortina\b(?=[\s\S]*\b(?:voil|linho)\b)(?=[\s\S]*\bsu[ií]co\b)", "cortina", "Cortina de voil e linho", "cortina", "cortina", "voil", "linho"),
    _rule(r"\bcaneta\b(?=[\s\S]*\b(?:caligrafia|cursiva)\b)(?=[\s\S]*\b(?:escreva|apague|reutiliz[aá]vel)\b)", "", "Caneta para caligrafia", "caneta", "caneta", "caligrafia", "cursiva"),
    _rule(r"\barm[aá]rio\b.*\bsapateira\b.*\bportas?\b", "", "Sapateira com portas", "sapateira", "sapateira", "sapateira", "portas"),
    _rule(r"\b(?:cascata|cortina)\b(?=[\s\S]*\b(?:natal|decora[cç][aã]o)\b)(?=[\s\S]*\b(?:led|bolas)\b)", "", "Cortina de luzes natalina", "cortina", "natal", "cortina", "LED", "Natal"),
    _rule(r"\bprateleira\b.*\b(?:mdf|madeira)\b", "prateleira", "Prateleira em MDF", "prateleira", "prateleira", "MDF"),
    _rule(r"\b(?:sacos?|saquinhos?)\b(?=[\s\S]*\bcubos?\s+de\s+gelo\b)", "", "Saquinhos para cubos de gelo", "saco", "saco", "saquinhos", "gelo"),
    _rule(r"\bmascara\b.*\boleo\b.*\bmaca\b|\bmaca\b.*\b(?:mascara|[oó]leo)\b", "", "Máscara e óleo capilar", "mascara", "cabelo", "máscara", "óleo"),
    _rule(r"\besp[aá]tula\b.*\bescova\b.*\b(?:skin\s*care|pele|facial)\b", "", "Espátula para skincare", "espatula", "beleza", "espátula", "skincare"),
    _rule(r"\blanterna\b.*\b(?:chaveiro|pingente)\b.*\bled\b", "lanterna", "Lanterna de chaveiro", "lanterna", "lanterna", "chaveiro", "LED"),
    _rule(r"\bcopo\b.*\b(?:dosador|medidor)\b.*\b(?:massa|panqueca|bolo)\b", "copo", "Dosador de massa para panqueca", "dosador", "cozinha", "dosador", "massa"),
    _rule(r"\blumin[aá]ria\b.*\binterruptor\b.*\bled\b", "luminaria", "Luminária com interruptor", "luminaria", "luminaria", "interruptor", "LED"),
    _rule(r"\bmixer\b.*\b3\s+em\s+1\b", "mixer", "Mixer multifuncional", "mixer", "mixer", "3 em 1"),
    _rule(r"\binfusor\b.*\bch[aá]\b.*\b(?:inox|a[cç]o\s+inoxid[aá]vel)\b", "", "Infusor de chá em inox", "infusor", "cha", "chá", "inox"),
    _rule(r"\bdescascador\b.*\b(?:rotacional|rotativo|circular)\b", "descascador", "Descascador rotativo", "descascador", "descascador", "rotacional"),
    _rule(r"\bapoio\b.*\bp[eé]s?\b.*\bventosa\b|\bapoio\b.*\bventosa\b", "", "Apoio para pés com ventosa", "apoio", "banheiro", "apoio", "ventosa"),
    _rule(r"\besfoliantes?\b.*\bfragr[aâ]ncias?\b", "esfoliante esfoliantes", "Esfoliante em várias fragrâncias", "esfoliante", "esfoliante", "esfoliante", "fragrâncias"),
    _rule(r"\bvaso\b.*\b(?:balan[cç]o|balan[cç]a)\b.*\bsuculent", "vaso", "Vaso decorativo em balanço", "vaso", "vaso", "vaso", "balanço"),
    _rule(r"\b(?:maleta|estojo|caixa)\b.*\bmaquiagem\b.*\b(?:espelho|pinc[eé]is)\b.*\bled\b", "", "Maleta de maquiagem com LED", "maleta", "maquiagem", "maquiagem", "LED"),
    _rule(r"\b(?:caneta|pincel)\b.*\bsobrancelha\b.*\b(?:multi|cerdas?)\b", "", "Pincel para sobrancelha", "pincel", "beleza", "sobrancelha", "cerdas"),
    _rule(r"\bcropped\b.*\b(?:tomara\s+que\s+caia|nervura|tricot)\b", "cropped", "Cropped tomara que caia", "cropped", "cropped", "tomara que caia"),
    _rule(r"\brack\b.*\borganizad", "rack", "Rack organizador", "rack", "rack", "organizador"),
    _rule(r"\b(?:jel[- ]?fit\s+)?tint\b", "", "Tint labial", "tint", "beleza", "tint"),
    _rule(r"\bextratora\b.*\bport[aá]til\b.*\b(?:sof[aá]|colch[aã]o|tapete|spot\s+cleaner)\b", "", "Extratora portátil de limpeza", "extratora", "limpeza", "extratora", "portátil"),
    _rule(r"\bestante\b.*\b(?:banheiro|lavanderia)\b.*\bprateleiras?\b", "estante", "Estante organizadora para banheiro", "estante", "estante", "banheiro", "prateleiras"),
    _rule(r"\b(?:formador|modelador|rolinhos?)\b.*\bcachos\b", "", "Modelador de cachos", "modelador", "cabelo", "modelador", "cachos"),
    _rule(r"\b(?:kit|cole[cç][aã]o)\b.*\besmaltes?\b", "", "Coleção de esmaltes", "esmalte", "esmalte", "esmaltes"),
    _rule(r"\btesoura\b.*\bcorte\s+criativo\b", "tesoura", "Tesoura de corte criativo", "tesoura", "tesoura", "corte criativo"),
    _rule(r"\b(?:cesto|fruteira)\b.*\b(?:fruteira|multiuso)\b.*\bmadeira\b", "", "Fruteira com alça de madeira", "fruteira", "fruteira", "fruteira", "madeira"),
    _rule(r"\bvaporizador\b.*\bhigienizador\b", "vaporizador", "Vaporizador higienizador", "vaporizador", "vaporizador", "higienizador"),
    _rule(r"\bcortina\b.*\bblackout\b.*\bvelcro\b", "cortina", "Cortina blackout com velcro", "cortina", "cortina", "blackout", "velcro"),
    _rule(r"\bchuveiro\b.*\bducha\s+manual\b", "chuveiro", "Chuveiro com ducha manual", "chuveiro", "chuveiro", "ducha manual"),
    _rule(r"\bkit\b.*\bhigiene\b.*\bbeb[eê]\b", "", "Kit de higiene para bebê", "kit", "bebe", "higiene", "bebê"),
    _rule(r"\b(?:lavador|lava)\b.*\bpinc[eé]is\b", "", "Limpador de pincéis", "limpeza", "beleza", "limpeza", "pincéis"),
    _rule(r"\b(?:daily\s+)?mask\b.*\b(?:sheets?|folha|folhas)\b|\bfolha\s+de\s+mascara\b", "", "Máscara facial", "mascara", "mascara", "máscara facial"),
    _rule(r"\b(?:gato|gatos?)\b.*\bbola\b.*\b(?:brinquedo|interativo)\b", "", "Brinquedo de bola para gatos", "brinquedo", "gato", "bola", "gato"),
    _rule(r"\bporta[- ]temperos?\b.*\b(?:gir[aá]tor|inox)\b", "", "Porta-tempero giratório", "temperos", "temperos", "porta-tempero", "giratório"),
    _rule(r"\bdifusor\b.*\b(?:chama|chamas)\b", "difusor", "Difusor com efeito de chama", "difusor", "difusor", "chama"),
    _rule(r"\bmochila\b.*\b(?:stitch|infantil)\b.*\brosa\b", "mochila", "Mochila infantil rosa", "mochila", "mochila", "infantil", "rosa"),
    _rule(r"\bsaboneteira\b.*\b(?:autom[aá]tic[ao]|sensor)\b.*\b(?:sabonete|espuma)\b", "saboneteira", "Dispenser automático para sabonete", "saboneteira", "saboneteira", "automático", "sabonete"),
    _rule(r"\bcorretor\b.*\bpostura\b.*\binteligente\b", "", "Corretor de postura inteligente", "corretor", "postura", "corretor", "postura"),
    _rule(r"\bconjunto\b.*\binfantil\b.*\bmenina\b|\bconjunto\b.*\bmenina\b.*\binfantil\b", "", "Conjunto infantil feminino", "conjunto", "moda", "conjunto", "infantil", "menina"),
    _rule(r"\bpet\b(?=[\s\S]*\b(?:gato|c[aã]o|cachorro)\b)(?=[\s\S]*\b(?:cosplay|fantasia|traje)\b)", "", "Fantasia para pets", "fantasia", "pet", "fantasia", "pet"),
    _rule(r"\b(?:lip\s+case|case\s+labial)\b", "", "Capa para cosmético labial", "capa", "beleza", "lip case"),
    _rule(r"\bedp\b.*\bintense\b|\bintense\b.*\bedp\b", "", "Perfume intenso", "perfume", "perfume", "intense", "EDP"),
    _rule(r"\bedp\b.*\bunissex\b", "", "Perfume unissex", "perfume", "perfume", "EDP", "unissex"),
    _rule(r"\bedp\b", "", "Perfume para a rotina", "perfume", "perfume", "EDP"),
    _rule(r"\bkit\b(?=[\s\S]*\b(?:clareador|melasma|manchas?)\b)(?=[\s\S]*\b(?:virilha|axilas?|rosto|pele)\b)", "", "Cuidados para a pele", "kit", "beleza", "pele", "manchas"),
    _rule(r"\b(?:red\s+)?cushion\b", "", "Base cushion", "base", "maquiagem", "cushion"),
    _rule(r"\broupas?\b(?=[\s\S]*\b(?:c[aã]es?|cachorros?|pets?)\b)(?=[\s\S]*\b(?:abelha|abelhas)\b)", "", "Roupa de abelha para cães", "roupa", "pet", "roupa", "abelha", "cães"),
    _rule(r"\bconjunto\b.*\binfantil\b.*\bmasculino\b.*\b(?:aranha|spider)", "", "Conjunto infantil masculino", "conjunto", "moda", "conjunto", "infantil", "masculino"),
    _rule(r"\btampas?\b(?=[\s\S]*\blata\b)(?=[\s\S]*\bsilicone\b)(?=[\s\S]*\b(?:palha|canudo)\b)", "", "Tampa de silicone com canudo", "tampa", "cozinha", "tampa", "silicone", "canudo"),
    _rule(r"\b(?:two\s+piece\s+sets?|tops?\s+de\s+tanque)\b.*\b(?:feminina|feminino|ver[aã]o)\b|\b(?:feminina|feminino)\b.*\btwo\s+piece\s+sets?\b", "", "Conjunto feminino de duas peças", "conjunto", "moda", "conjunto", "duas peças"),
    _rule(r"\bstick\b(?=[\s\S]*\bfps\b)(?=[\s\S]*\b(?:cor|bege)\b)", "", "Protetor solar em bastão", "protetor", "protetor", "FPS", "stick"),
    _rule(r"\bkit\b(?=[\s\S]*\bherm[eé]tico\b)(?=[\s\S]*\btampa\b)(?=[\s\S]*\bcolher\b)", "", "Recipiente hermético com colher", "recipiente", "cozinha", "hermético", "colher"),
    _rule(r"\b(?:diamond\s+rings?|engagement\s+ring|anel\s+de\s+noivado)\b", "", "Anel para noivado", "anel", "anel", "anel", "noivado"),
    _rule(r"\bequipamento\b.*\bfitness\b.*\bdobr[aá]vel\b", "", "Equipamento de treino dobrável", "equipamento", "fitness", "fitness", "dobrável"),
    _rule(r"\bconjunto\b.*\bsacolas?\b|\bsacolas?\b.*\bconjunto\b", "", "Conjunto de sacolas", "sacola", "sacola", "conjunto", "sacolas"),
    _rule(r"\brabo\s+de\s+cavalo\b.*\bondulad", "", "Rabo de cavalo ondulado", "cabelo", "cabelo", "rabo de cavalo", "ondulado"),
    _rule(r"\bmicro[- ]?ondas?\b", "", "Micro-ondas para cozinha", "microondas", "microondas", "micro-ondas"),
    _rule(r"\bprote[cç][aã]o\b.*\bpalma\b.*\b(?:borracha|halteres?|peso)\b", "", "Grip antiderrapante para treino", "grip", "fitness", "grip", "antiderrapante", "treino"),
    _rule(r"\brealme\b.*\b(?:4g|5g)\b", "", "Celular para o cotidiano", "celular", "celular", "4G"),
    _rule(r"\blip\s+oil\b(?=[\s\S]*\b(?:berry|berries|frutas?)\b)|\b(?:berry|berries)\b(?=[\s\S]*\blip\s+oil\b)", "", "Óleo labial de frutas vermelhas", "oleo", "beleza", "lip oil", "berry"),
    _rule(r"\bpalette?\b.*\bsombras?\b|\bpaleta\b.*\bsombras?\b", "", "Paleta de sombras neutras", "paleta", "maquiagem", "paleta", "sombras"),
    _rule(r"\bchapinha\b.*\b(?:cachead[oa]s?|alisador)\b|\balisador\b.*\bcabelos?\b", "", "Chapinha para cabelos cacheados", "chapinha", "cabelo", "chapinha", "cabelos"),
    _rule(r"\bcorretivo\b.*\bmatte\b", "", "Corretivo com acabamento matte", "corretivo", "corretivo", "corretivo", "matte"),
    _rule(r"\bba[uú]\b.*\b(?:suede|veludo)\b", "", "Baú revestido em veludo", "bau", "bau", "baú", "veludo"),
    _rule(r"\bkit\b.*\b(?:unboxing|embalar|pedidos)\b", "", "Kit para embalar pedidos", "kit", "papelaria", "unboxing", "pedidos"),
    _rule(r"\bar[- ]condicionado\b.*\bport[aá]til\b.*\bwi[- ]?fi\b", "", "Ar-condicionado portátil com Wi-Fi", "arcondicionado", "arcondicionado", "portátil", "Wi-Fi"),
    _rule(r"\borganizadoras?\b.*\bacr[ií]lico\b.*\b(?:casa|escrit[oó]rio)\b", "", "Organizadores de acrílico", "organizador", "organizador", "organizadores", "acrílico"),
    _rule(r"\bborracha\b.*\bperfumad[ao]\b.*\bmorango\b", "", "Borracha perfumada de morango", "borracha", "papelaria", "perfumada", "morango"),
    _rule(r"\b(?:red\s+booster|booster\s+riddle\s+shot)\b", "", "Booster cosmético", "booster", "beleza", "booster"),
    _rule(r"\bporta[- ]ovos?\b.*\bpinguim\b|\bpinguim\b.*\bporta[- ]ovos?\b", "", "Porta-ovos de pinguim", "portaovos", "cozinha", "porta-ovos", "pinguim"),
    _rule(r"\b(?:t[- ]?shirt|camiseta)\b(?=[\s\S]*\bbordad[ao]\b)(?=[\s\S]*\balgod[aã]o\b)", "", "Camiseta bordada de algodão", "camiseta", "camiseta", "bordada", "algodão"),
    _rule(r"\bmarca[- ]?texto\b(?=[\s\S]*\bfibra\b)(?=[\s\S]*\bpastel\b)", "", "Marca-texto de ponta de fibra", "marcatexto", "papelaria", "ponta de fibra", "pastel"),
    _rule(r"\bescad(?:a|inha)\b(?=[\s\S]*\b(?:pet|c[aã]es?|cachorro|gatos?)\b)", "", "Escadinha para cães", "escadinha", "pet", "escadinha", "cães"),
    _rule(r"\bchapinha\b.*\bprofissional\b", "", "Chapinha profissional para cabelo", "chapinha", "cabelo", "chapinha", "profissional"),
    _rule(r"\bespuminhas?\b.*\b(?:carnaval|neve)\b", "", "Espuma de neve para Carnaval", "espuma", "carnaval", "espuma", "neve"),
    _rule(r"\bembalagens?\b.*\bblister\b.*\bovos?\b.*\bp[aá]scoa\b", "", "Blister para ovos de Páscoa", "blister", "pascoa", "blister", "ovo", "Páscoa"),
    _rule(r"\bembalagem\b.*\bovos?\s+de\s+colher\b", "", "Caixa para ovos de colher", "caixa", "pascoa", "ovos de colher"),
    _rule(r"\blembrancinhas?\b.*\bp[aá]scoa\b|\bkit\b.*\blembrancinha\b.*\bp[aá]scoa\b", "", "Lembrancinhas de Páscoa", "lembrancinha", "pascoa", "lembrancinha", "Páscoa"),
    _rule(r"\b(?:mixer|badge\s*mixer)\b.*\bautom[aá]tico\b.*\b(?:sopas?|molhos?|cremes?)\b", "", "Mixer automático para cozinha", "mixer", "mixer", "automático", "cozinha"),
    _rule(r"\bcolher\b(?=[\s\S]*\bmedidor[ao]\b)(?=[\s\S]*\bajust[aá]vel\b)", "", "Colher medidora ajustável", "colher", "cozinha", "medidora", "ajustável"),
    _rule(r"\bquartzo\b.*\b[aá]\s+prova\s+d['’]?[aá]gua\b|\bquartzo\b.*\bcasual\b", "", "Relógio de quartzo", "relogio", "relogio", "quartzo"),
    _rule(r"\bconjunto\b.*\bjardim\b.*\bestofad[oa]\b", "", "Conjunto estofado para jardim", "conjunto", "jardim", "conjunto", "jardim", "estofado"),
    _rule(r"\bborracha\b.*\bescolar\b.*\bmacia\b", "", "Borracha escolar macia", "borracha", "papelaria", "escolar", "macia"),
    _rule(r"\bdaily\s+mask\b.*\b(?:sheets?|folhas?)\b|\bdaily\s+mask\b", "", "Máscara facial diária", "mascara", "mascara", "daily mask"),
    _rule(r"\bregenerador\b.*\blabial\b|\blabial\b.*\bregenerador\b", "", "Cuidado labial regenerador", "cuidado", "beleza", "labial", "regenerador"),
    _rule(r"\bkit\b(?=[\s\S]*\bcabelos?\s+cachead[oa]s?\b)(?=[\s\S]*\bcachos\b)", "", "Kit para cabelos cacheados", "kit", "cabelo", "cabelos cacheados", "cachos"),
    _rule(r"\bguarda[- ]?chuva\b.*\bautom[aá]tico\b", "", "Guarda-chuva automático", "guarda-chuva", "chuva", "automático"),
    _rule(r"\bsab[aã]o\s+l[ií]quido\b", "", "Sabão líquido para lavagem", "sabao", "limpeza", "sabão líquido"),
    # Catalog coverage: common product classes absent from the original
    # title-rule set. These captions use only the class and details stated in
    # the Vision title; they avoid brands, model numbers, and sales language.
    _rule(r"\bar[- ]condicionado\b", "", "Climatização para casa", "arcondicionado", "arcondicionado", "ar-condicionado"),
    _rule(r"\blava\s+e\s+seca\b", "", "Lavadora e secadora", "lavaseca", "lavaseca", "lava e seca"),
    _rule(r"\b(?:eau\s+de\s+parfum|parfum|perfume)\b", "", "Fragrância para rotina", "perfume", "perfume", "eau de parfum"),
    _rule(r"\b(?:smartphone|celular|infinix\s+(?:note|smart)|redmi\s+\d|xiaomi\s+(?:poco|redmi)|poco\s+x\d|realme\s+[a-z]?\d|redmagic\s+\d|uranyx\s+[a-z]\d)\b", "", "Celular no cotidiano", "celular", "celular", "smartphone"),
    _rule(r"\b(?:game\s*stick|videogame\s*stick|video\s+game\s+retro)\b", "", "Jogos retrô na tela", "videogame", "videogame", "game stick"),
    _rule(r"\b(?:dji\s+osmo|action\s+camera|c[aâ]mera\s+de\s+a[cç][aã]o)\b", "", "Câmera para registrar momentos", "camera", "camera", "câmera"),
    _rule(r"\bkindle\b", "", "Leitura no Kindle", "kindle", "leitura", "Kindle"),
    _rule(r"\b(?:echo\s+show|speaker\s+amazon|smart\s+speaker|alto[- ]falante\s+inteligente)\b", "", "Som e voz em casa", "speaker", "speaker", "speaker"),
    _rule(r"\bheadset\b", "", "Headset para ouvir e jogar", "headset", "headset", "headset"),
    _rule(r"\b(?:wireless\s+bluetooth\s+earphone|bluetooth\s+earphone|fone\s+de\s+ouvido)\b", "", "Fone Bluetooth no cotidiano", "fone", "fone", "earphone"),
    _rule(r"\bsmart\s*band\b", "", "Rotina acompanhada no pulso", "smartband", "smartband", "smartband"),
    _rule(r"\bmem[oó]ria\b(?=[\s\S]*\b(?:ddr|ram|computador)\b)", "", "Memória para computador", "memoria", "memoria", "memória", "computador"),
    _rule(r"\bgravador\s+de\s+voz\b|\bplaud\s+note\b", "", "Gravações em um dispositivo compacto", "gravador", "gravador", "gravador de voz"),
    _rule(r"\b(?:porta[- ]p[aã]o|porta\s+p[aã]es?)\b", "", "Porta-pão de bambu", "portapao", "portapao", "porta-pão", "bambu"),
    _rule(r"\bcristaleira\b", "", "Cristaleira com portas de vidro", "cristaleira", "cristaleira", "cristaleira", "vidro"),
    _rule(r"\bcobre[- ]?leito\b(?=[\s\S]*\bpercal\b)", "", "Cobre-leito em percal", "cobreleito", "cobreleito", "cobre-leito", "percal"),
    _rule(r"\bcercas?\s+pl[aá]sticas?\b", "", "Cercas decorativas para o jardim", "cerca", "jardim", "cercas", "jardim"),
    _rule(r"\bporta[- ]chaves?\b", "", "Porta-chaves para a parede", "portachaves", "portachaves", "porta-chaves", "parede"),
    _rule(r"\bm[uú]lt[ií]uso\b(?=[\s\S]*\bportas?\b)", "", "Armário multiuso", "armario", "armario", "multiuso", "portas"),
    _rule(r"\bbra[cç]o\s+de\s+eleva[cç][aã]o\b", "", "Braço de elevação para construção", "braco", "braco", "braço de elevação"),
    _rule(r"\b(?:n[uú]mero\s+residencial|n[uú]mero\s+de\s+resid[eê]ncia)\b", "", "Número residencial em aço corten", "numero", "numero", "número residencial", "aço corten"),
    _rule(r"\b(?:mai[oô]|mai[oô]s)\b", "", "Estampa de ondas", "maio", "maio", "maiô", "estampa onda"),
    _rule(r"\b(?:tubar[aã]o|miniatura)\b(?=[\s\S]*\barticulad[oa]\b)", "", "Miniatura articulada de tubarão", "miniatura", "brinquedo", "miniatura", "tubarão", "articulada"),
    _rule(r"\bcasinha\b(?=[\s\S]*\b(?:constru[cç][aã]o|montar|ecobrick)\b)", "", "Casinha de montar", "casinha", "casinha", "casinha", "montar"),
    _rule(r"\bconjunto\b(?=[\s\S]*\bfitness\b)(?=[\s\S]*\b(?:c[oó]s|bojo|forro)\b)", "", "Conjunto para treino", "conjunto", "fitness", "conjunto", "fitness"),
    _rule(r"\bconjunto\b(?=[\s\S]*\b(?:infantil|juvenil)\b)(?=[\s\S]*\bmasculino\b)", "", "Conjunto infantil masculino", "conjunto", "moda", "conjunto", "infantil"),
    _rule(r"\bconjunto\b(?=[\s\S]*\b(?:infantil|juvenil)\b)(?=[\s\S]*\bmenina\b)", "", "Conjunto infantil feminino", "conjunto", "moda", "conjunto", "infantil"),
    _rule(r"\b(?:shorts?\s*feminino|shorts?\s+feminino|shorts?feminino)\b(?=[\s\S]*\blinho\b)", "", "Short de linho", "short", "short", "short feminino", "linho"),
    _rule(r"\bparka\b(?=[\s\S]*\bl[aã]\s+batida\b)", "", "Parka forrada para o frio", "parka", "parka", "parka", "forrada"),
    _rule(r"\b(?:cole[cç][aã]o|atividades?)\b(?=[\s\S]*\b(?:dinossauros?|bluey|animais\s+fofinhos)\b)", "", "Atividades para brincar e aprender", "atividade", "brinquedo", "atividades"),
    _rule(r"\bquebra[- ]?cabe[cç]a\b", "", "Quebra-cabeça para montar", "quebracabeca", "quebracabeca", "quebra-cabeça"),
    _rule(r"\bprancheta\b(?=[\s\S]*\b(?:pintar|aquarela)\b)", "", "Prancheta para pintar com aquarela", "prancheta", "prancheta", "prancheta", "aquarela"),
    _rule(r"\b(?:coloring\s+book|livro\s+de\s+colorir|livro\s+[\w\s-]{0,35}\bcolorir)\b", "", "Livro para colorir", "livro", "livro", "livro", "colorir"),
    _rule(r"\b(?:devocional|ora[cç][aã]o\s*\|)\b", "", "Leitura para momentos de reflexão", "livro", "leitura", "devocional"),
    _rule(r"\b(?:mais\s+esperto\s+que\s+o\s+diabo|dicion[aá]rio\s+escolar|dicion[aá]rio\s+pequeno)\b", "", "Leitura para ampliar o repertório", "livro", "livro", "dicionário"),
    _rule(r"\b(?:porta[- ]p[aã]o|porta\s+p[aã]es?)\b", "", "Porta-pão de bambu", "portapao", "portapao", "porta-pão", "bambu"),
    _rule(r"\b(?:bule|chaleira)\b(?=[\s\S]*\bvidro\b)(?=[\s\S]*\bfogo\b)", "", "Bule de vidro para fogo", "bule", "bule", "bule", "vidro", "fogo"),
    _rule(r"\b(?:tampa\s+multiuso|tampa\s+de\s+silicone)\b(?=[\s\S]*\bvapor\b|[\s\S]*\bcozimento\b)", "", "Tampa de silicone para cozimento", "tampa", "cozinha", "tampa de silicone", "cozimento"),
    _rule(r"\b(?:brigadeiro|recheio\s+e\s+cobertura)\b", "", "Sabor de chocolate na cozinha", "doce", "doce", "brigadeiro"),
    _rule(r"\b(?:recheio\s+e\s+cobertura|cobertura\s+de\s+morango)\b", "", "Recheio de morango para receitas", "recheio", "receitas", "recheio", "morango"),
    _rule(r"\b(?:fralda|absorvente\s+externo)\b", "", "Cuidados para a rotina", "higiene", "higiene", "fralda"),
    _rule(r"\b(?:soro\s+fisiol[oó]gico|[aá]gua\s+micelar)\b", "", "Cuidado na rotina", "cuidado", "cuidado", "soro fisiológico"),
    _rule(r"\b(?:repelente)\b", "", "Repelente para a rotina", "repelente", "repelente", "repelente"),
    _rule(r"\b(?:dilatador\s+nasal|depilador)\b", "", "Cuidado pessoal na rotina", "cuidados", "cuidados", "depilador"),
    _rule(r"\b(?:massageador|massegeador)\b(?=[\s\S]*\bpesco[cç]o\b)", "", "Massagem para o pescoço", "massageador", "massageador", "pescoço", "massagem"),
    _rule(r"\b(?:whey\s+protein|whey\s+isolado|prote[ií]na\s+\d)\b", "", "Whey protein para a rotina", "whey", "whey", "whey protein"),
    _rule(r"\b(?:pr[eé][- ]?treino|pre[- ]?workout)\b", "", "Pré-treino para a rotina", "suplemento", "suplemento", "pré-treino"),
    _rule(r"\b(?:depilador)\b(?=[\s\S]*\b(?:facial|corporal|recarreg[aá]vel)\b)", "", "Depilador para cuidados pessoais", "depilador", "depilador", "depilador"),
    _rule(r"\b(?:escova\s+el[eé]trica|electric\s+toothbrush)\b", "", "Escova elétrica para a rotina", "escova", "escova", "escova elétrica"),
    _rule(r"\b(?:ampoule|ampola)\b", "", "Ampola para cuidado facial", "ampola", "pele", "ampoule"),
    _rule(r"\b(?:suncream|sunstick|protetor\s+solar)\b", "", "Proteção solar na rotina", "protetor", "protetor", "protetor solar"),
    _rule(r"\b(?:retinal|capsule\s+cream|barrier\s+cream|relief\s+cream|cream)\b", "", "Creme para a pele", "creme", "pele", "cream"),
    _rule(r"\b(?:kit\s+\d+\s+reparador\s+de\s+pontas|oil\s+reparador|reparador\s+de\s+pontas)\b", "", "Cuidado para os fios", "cuidado", "cabelo", "reparador"),
    _rule(r"\b(?:tintura|tonalizante)\b(?=[\s\S]*\bcabelo\b|[\s\S]*\bruivo\b)", "", "Tonalidade para os cabelos", "tonalizante", "cabelo", "tonalizante"),
    _rule(r"\b(?:micelar)\b(?=[\s\S]*\b(?:agua|garnier)\b)", "", "Água micelar na rotina facial", "agua", "agua", "água micelar"),
    _rule(r"\b(?:serum|s[eé]rum)\b", "", "Sérum para cuidados com a pele", "serum", "pele", "sérum"),
    _rule(r"\b(?:talco)\b", "", "Talco para a rotina", "talco", "talco", "talco"),
    _rule(r"\b(?:lily\s+gardenia|coffee\s+woman|una\s+artisan|botica\s+214|her\s+code|amnia\s+al\s+wataniah|212\s+sexy|xerjoff\s+naxos)\b", "", "Fragrância para rotina", "perfume", "perfume", "eau de parfum"),
    _rule(r"\b(?:kit\s+\d+\s+hidratantes?|hidratantes?\s+nivea)\b", "", "Hidratação para a rotina", "hidratante", "hidratante", "hidratante"),
    _rule(r"\b(?:kit\s+banheiro|kit\s+para\s+banheiro|lavabo)\b(?=[\s\S]*\bvidro\b)(?=[\s\S]*\bambar\b)", "", "Vidro âmbar no lavabo", "lavabo", "lavabo", "lavabo", "vidro", "âmbar"),
    _rule(r"\b(?:a[cç]ucareiro|saleiro|manteigueira|bomboni[eè]re)\b", "", "Detalhes para servir à mesa", "mesa", "mesa", "açucareiro"),
    _rule(r"\b(?:ralador|picador|triturador)\b(?=[\s\S]*\b(?:cozinha|queijo|gelo|alho)\b)", "", "Preparo prático na cozinha", "cozinha", "cozinha", "ralador"),
    _rule(r"\b(?:ralador\s+de\s+queijo)\b(?=[\s\S]*\bcompartimento\b)", "", "Ralador de queijo com reservatório", "ralador", "ralador", "ralador de queijo", "reservatório"),
    _rule(r"\b(?:tostadeira|air\s*fryer|cozedor\s+de\s+ovos|egg\s+cooker)\b", "", "Preparo na cozinha", "cozinha", "cozinha", "cozinha"),
    _rule(r"\b(?:kit\s+feijoada|conjunto\s+de\s+ch[aá]|cj\s+de\s+ch[aá])\b", "", "Conjunto para servir à mesa", "conjunto", "mesa", "conjunto", "cerâmica"),
    _rule(r"\b(?:garrafa\s+t[eé]rmica|botij[aã]o\s+t[eé]rmico)\b", "", "Bebidas na temperatura desejada", "garrafa", "garrafa", "térmico"),
    _rule(r"\b(?:cerveja|barril\s+heineken)\b", "", "Cerveja para compartilhar", "cerveja", "cerveja", "cerveja"),
    _rule(r"\b(?:banana|bananinha|pa[cç]oquita|doce\s+de\s+amendoim)\b", "", "Um doce para a pausa", "doce", "doce", "doce"),
    _rule(r"\b(?:laranjas?\s+desidratadas?|mix\s+de\s+frutas\s+desidratadas?)\b", "", "Frutas para acompanhar a pausa", "frutas", "frutas", "frutas"),
    _rule(r"\b(?:soro\s+fisiol[oó]gico)\b", "", "Soro fisiológico para a rotina", "soro", "soro", "soro fisiológico"),
    _rule(r"\b(?:amora\s+miura|zamiocuca)\b", "", "Cultivo de plantas em casa", "plantas", "plantas", "plantas"),
    _rule(r"\b(?:n[uú]mero\s+residencial)\b", "", "Número para identificar a residência", "numero", "numero", "número residencial"),
    _rule(r"\b(?:totem\s+de\s+ch[aã]o|display\s+totem)\b", "", "Totem personalizado para a festa", "totem", "totem", "totem", "personalizado"),
    _rule(r"\b(?:p[eé]\s+palito|mesinhas?\s+laterais?)\b", "", "Mesinhas laterais para a sala", "mesinha", "mesinha", "mesinhas laterais"),
    _rule(r"\b(?:esmerilhadeira|lixadeira\s+angular)\b", "", "Ferramenta para corte e desbaste", "ferramenta", "ferramenta", "esmerilhadeira"),
    _rule(r"\b(?:martelo\s+perfurador|rompedor)\b", "", "Ferramenta para perfuração", "ferramenta", "ferramenta", "martelo perfurador"),
    _rule(r"\b(?:escada\s+telesc[oó]pica)\b", "", "Escada telescópica compacta", "escada", "escada", "escada telescópica"),
    _rule(r"\b(?:colhedor\s+de\s+frutas)\b", "", "Colheita de frutas ao alcance", "colhedor", "colhedor", "colhedor de frutas"),
    _rule(r"\b(?:raquete\s+el[eé]trica)\b", "", "Raquete elétrica contra mosquitos", "raquete", "raquete", "raquete elétrica"),
    _rule(r"\b(?:cadeado\s+antifurto)\b", "", "Cadeado antifurto para motocicleta", "cadeado", "cadeado", "cadeado antifurto"),
    _rule(r"\b(?:retrovisor\s+interno)\b", "", "Visão panorâmica para o carro", "retrovisor", "retrovisor", "retrovisor interno"),
    _rule(r"\b(?:insulfilm|p[aá]ra[- ]brisas?)\b", "", "Proteção solar para os vidros", "vidro", "vidro", "insulfilm"),
    _rule(r"\b(?:aditivo\s+de\s+radiador)\b", "", "Aditivo para o radiador", "aditivo", "aditivo", "radiador"),
    _rule(r"\b(?:veda\s+porta|veda[- ]porta)\b", "", "Vedação contra poeira", "vedacao", "vedacao", "veda porta"),
    _rule(r"\b(?:piso\s+estrado\s+modular|deck\s+modular)\b", "", "Piso modular para diferentes espaços", "piso", "piso", "piso modular"),
    _rule(r"\b(?:tecla\s+enter\s+gigante)\b", "", "Tecla Enter antiestresse", "tecla", "tecla", "tecla Enter"),
    _rule(r"\b(?:revolu[cç][aã]o\s+mec[aâ]nica|teclado\s+switch)\b", "", "Teclado compacto para a mesa", "teclado", "teclado", "teclas"),
    _rule(r"\b(?:encadernadora)\b", "", "Encadernação para projetos criativos", "encadernadora", "encadernadora", "encadernadora"),
    _rule(r"\b(?:marca[- ]?texto|marcador\s+de\s+texto)\b", "", "Cores para marcar e organizar", "marcatexto", "marcatexto", "marca-texto"),
    _rule(r"\b(?:apontador)\b", "", "Apontador para a rotina escolar", "apontador", "apontador", "apontador"),
    _rule(r"\b(?:apagador\s+de\s+cor|borracha\s+(?:escolar|de\s+apagar|para\s+l[aá]pis))\b", "", "Apoio para escrever e desenhar", "papelaria", "papelaria", "apagador"),
    _rule(r"\b(?:dicion[aá]rio|livro|book)\b", "", "Leitura para acompanhar o dia", "livro", "livro", "livro"),
    _rule(r"\b(?:kalimba|piano\s+de\s+dedo)\b", "", "Música ao alcance dos dedos", "instrumento", "instrumento", "kalimba"),
    _rule(r"\b(?:porta[- ]queijos?)\b", "", "Porta-queijo para servir à mesa", "portaqueijo", "portaqueijo", "porta-queijo"),
    _rule(r"\b(?:tampa\s+protetora\s+de\s+fritura)\b", "", "Tela contra respingos na cozinha", "tela", "tela", "tampa protetora", "fritura"),
    _rule(r"\b(?:sugador\s+de\s+picada|extrator\s+de\s+veneno)\b", "", "Extrator para picadas de insetos", "extrator", "extrator", "sugador de picada"),
    _rule(r"\b(?:marca[- ]?p[aá]ginas?)\b", "", "Marca-páginas para personalizar", "marcapaginas", "marcapaginas", "marca-páginas"),
    _rule(r"\b(?:borrachas?\s+fofas?|apagador\s+de\s+cor)\b", "", "Detalhes divertidos para a papelaria", "papelaria", "papelaria", "borracha"),
    _rule(r"\b(?:kit\s+volta\s+[aà]s\s+aulas|kit\s+papelaria)\b", "", "Papelaria para as aulas", "papelaria", "papelaria", "papelaria"),
    _rule(r"\b(?:bandejas?\s+bordadas?)\b", "", "Bandejas com detalhe bordado", "bandeja", "bandeja", "bandeja", "bordado"),
    _rule(r"\b(?:porta[- ]queijos?|manteigueira|bomboni[eè]re)\b", "", "Detalhes para servir à mesa", "mesa", "mesa", "mesa"),
    _rule(r"\b(?:mini\s+guarda[- ]?chuva|sombrinha)\b", "", "Sombrinhas para a chuva", "sombrinha", "sombrinha", "sombrinha"),
    _rule(r"\b(?:avi[aã]o\s+com\s+lan[cç]ador)\b", "", "Avião com lançador para brincar", "aviao", "brinquedo", "avião", "lançador"),
    _rule(r"\b(?:boneca|mini\s+bonecas?|beb[eê]s?\s+reborn)\b", "", "Bonecas para brincar e colecionar", "boneca", "boneca", "boneca"),
    _rule(r"\b(?:stair[- ]climbing\s+toy|duck\s+climbing\s+stairs)\b", "", "Brinquedo de escadinha com luzes", "brinquedo", "brinquedo", "toy", "lights"),
    _rule(r"\b(?:bate\s+dog|cachorrinho\s+com\s+martelo)\b", "", "Brinquedo de martelo e bolinhas", "brinquedo", "brinquedo", "martelo", "bolinhas"),
    _rule(r"\b(?:play[- ]?doh|massinha)\b", "", "Massinha para brincadeiras criativas", "massinha", "massinha", "massinha"),
    _rule(r"\b(?:hot\s+wheels|personagens\s+disney|racerverse)\b", "", "Personagens para brincar e colecionar", "brinquedo", "brinquedo", "personagens"),
    _rule(r"\b(?:cole[cç][aã]o\s+natalina|lata\s+natal|natalina\s+flocos)\b", "", "Detalhes para celebrar o Natal", "natal", "natal", "Natal"),
    _rule(r"\b(?:kit\s+presente|combo\s+presente)\b(?=[\s\S]*\b(?:namorados?|m[aã]es|natal|anivers[aá]rio)\b)", "", "Um presente para momentos especiais", "presente", "presente", "kit presente"),
    _rule(r"\b(?:tuff\s+sem\s+passar|desamassa\s+e\s+neutraliza\s+odores)\b", "", "Cuidado com as roupas", "roupas", "roupas", "desamassa"),
    _rule(r"\b(?:limpadores?\s+coala|combo\s+\d+\s+limpadores?)\b", "", "Limpeza perfumada para a casa", "limpeza", "limpeza", "limpadores"),
    _rule(r"\b(?:poderoso\s+brilha\s+inox|brilha\s+inox)\b", "", "Brilho para superfícies de inox", "inox", "inox", "brilha inox"),
    _rule(r"\b(?:retalho\s+liso\s+ou\s+estampado|pacote\s+de\s+retalho)\b", "", "Retalhos lisos ou estampados", "retalho", "retalho", "retalho"),
    _rule(r"\b(?:crinol\s+tubular)\b", "", "Crinol tubular para trabalhos manuais", "crinol", "crinol", "crinol"),
    _rule(r"\b(?:fio[s]?\s+de\s+cabelo\s+coloridos?|fios?\s+sint[eé]ticos?\s+hologr[aá]ficos?)\b", "", "Fios coloridos com efeito holográfico", "cabelo", "cabelo", "fios coloridos"),
    _rule(r"\b(?:esponja\s+de\s+limpeza|barbeador\s+de\s+tecido)\b", "", "Cuidado com os tecidos", "tecido", "tecido", "tecido"),
    _rule(r"\b(?:cozinha\s+compacta)\b", "", "Cozinha compacta", "cozinha", "cozinha", "cozinha compacta"),
    _rule(r"\b(?:plantador\s+inteligente|vaso\s+inteligente)\b", "", "Cultivo de plantas em casa", "plantas", "plantas", "plantador"),
    _rule(r"\b(?:kit\s+de\s+el[aá]sticos\s+para\s+treino)\b", "", "Elásticos para acompanhar o treino", "elastico", "elastico", "elásticos", "treino"),
    _rule(r"\b(?:carrinho\s+de\s+brinquedo|carros?\s+decora[cç][aã]o\s+de\s+casa)\b", "", "Carros em miniatura para brincar", "carro", "carro", "carros"),
    _rule(r"\b(?:autom[aá]tico|sensor)\b(?=[\s\S]*\b(?:lixeira|lata\s+de\s+lixo)\b)", "", "Lixeira com abertura automática", "lixeira", "lixeira", "lixeira", "automática"),
    _rule(r"\b(?:c[aâ]mera\s+de\s+a[cç][aã]o|osmo\s+action|osmo\s+pocket)\b", "", "Câmera para registrar momentos", "camera", "camera", "câmera"),
    _rule(r"\b(?:misturador|batedor)\s+el[eé]trico\b", "", "Preparo prático na cozinha", "cozinha", "cozinha", "cozinha"),
    _rule(r"\b(?:velas?|aromatizador)\b(?=[\s\S]*\bess[eê]ncias?\b)", "", "Aromas para perfumar o ambiente", "aroma", "aroma", "aromatizador"),
    _rule(r"\b(?:porta[- ]chaves?|chaveiro)\b", "", "Chaves sempre por perto", "chaves", "chaves", "chaves"),
    _rule(r"\b(?:livro|dicion[aá]rio|devocional)\b", "", "Leitura para acompanhar o dia", "livro", "livro", "livro"),
    _rule(r"\b(?:kit\s+de\s+massinha|massinha\s+play)\b", "", "Massinha para brincadeiras criativas", "massinha", "massinha", "massinha"),
    _rule(r"\b(?:ralador\s+de\s+queijo|picador\s+de\s+gelo)\b", "", "Preparo prático na cozinha", "cozinha", "cozinha", "ralador"),
    _rule(r"\b(?:panela\s+el[eé]trica|panela\s+de\s+press[aã]o)\b", "", "Preparo na cozinha", "panela", "panela", "panela"),
    _rule(r"\b(?:beb[eê]\s+granado|tradicional\s+beb[eê])\b", "", "Fragrância delicada para o bebê", "perfume", "perfume", "eau de cologne"),
    _rule(r"\b(?:suporte\s+para\s+xiaomi|case\s+elvev|para\s+xiaomi)\b", "", "Acessório para celular", "acessorio", "celular", "para xiaomi"),
    _rule(r"\b(?:tampa\s+para\s+leite|tampa\s+para\s+mamadeira)\b", "", "Tampa para utensílio de alimentação", "tampa", "tampa", "tampa"),
    _rule(r"\b(?:linha\s+refinatto|vidro\s+com\s+borda\s+dourada)\b", "", "Vidro com detalhe dourado", "vidro", "vidro", "vidro", "borda dourada"),
    _rule(r"\b(?:kit\s+colmeia\s+organizadora|organizadora\s+de\s+gavetas)\b", "", "Organização para as gavetas", "organizacao", "organizacao", "organizadora", "gavetas"),
    _rule(r"\b(?:colher\s+de\s+frutas|colhedor\s+de\s+frutas)\b", "", "Colheita de frutas ao alcance", "colhedor", "colhedor", "frutas"),
    _rule(r"\b(?:brinquedo\s+de\s+escada|toy,\s*duck)\b", "", "Brinquedo para acompanhar a brincadeira", "brinquedo", "brinquedo", "toy"),
    _rule(r"\b(?:fwee\s+lip\s*&\s*cheek|lip\s+&\s+cheek)\b", "", "Cor para lábios e bochechas", "maquiagem", "maquiagem", "lip", "cheek"),
    _rule(r"\b(?:tecla\s+enter|teclado)\b", "", "Teclas para acompanhar a rotina", "teclado", "teclado", "teclado"),
    _rule(r"\bbiquin(?:i|e)\b", "", "Estampa de ondas", "biquini", "biquini", "biquíni", "estampa"),
    _rule(r"\bsai\s+everlopad[oa]\b|\bsaia\b(?=[\s\S]*\b(?:transpassad[oa]|envelopad[oa])\b)", "", "Saia transpassada", "saia", "saia", "saia", "transpassada"),
    _rule(r"\b(?:kit\s+siage|siage\s+acelera\s+o\s+crescimento)\b", "", "Cuidado capilar na rotina", "cabelo", "cabelo", "siage", "cabelo"),
    _rule(r"\b(?:sheglam\s+cole[cç][aã]o|cole[cç][aã]o\s+harry\s+potter)\b", "", "Coleção de maquiagem", "maquiagem", "maquiagem", "sheglam"),
    _rule(r"\b(?:medicube\s+age[- ]?r\s+booster\s+pro)\b", "", "Cuidado facial com tecnologia", "beleza", "beleza", "booster pro"),
    _rule(r"\b(?:kit\s+n[aã]o\s+chore\s+mais|borabella\s+progressiva)\b", "", "Cuidado capilar na rotina", "cabelo", "cabelo", "borabella"),
    _rule(r"\b(?:kit\s+\d+\s+produtos?\s+morte\s+s[uú]bita|lola\s+cosmetics\s+morte\s+s[uú]bita)\b", "", "Cuidados para os fios", "cabelo", "cabelo", "morte súbita"),
    _rule(r"\b(?:curaprox\s+pink\s+edition|curaprox\s+travel\s+set)\b", "", "Escova dental para a rotina", "escova", "escova", "curaprox"),
    _rule(r"\b(?:cuide[- ]?se\s+bem|morango\s+e\s+leite)\b", "", "Cuidado perfumado na rotina", "beleza", "beleza", "cuide-se bem"),
    _rule(r"\b(?:lua\s*&\s*neve|five\s+senses\s+collection)\b", "", "Aromas para a rotina", "aroma", "aroma", "five senses"),
    _rule(r"\b(?:ora[cç][aã]o\s*\||descobrindo\s+o\s+poder\s+de\s+falar\s+com\s+deus)\b", "", "Leitura para momentos de reflexão", "livro", "livro", "oração"),
    _rule(r"\b(?:kit\s+caixinhas?\s+para\s+festa|caixinhas?\s+para\s+festa)\b", "", "Caixinhas para celebrar", "caixinhas", "festa", "caixinhas", "festa"),
    _rule(r"\b(?:pads?\s+peito|falsos?\s+m[uú]sculos|male\s+protective\s+sponge)\b", "", "Pads para modelagem do peitoral", "pads", "moda", "pads", "peito"),
    _rule(r"\b(?:kit\s+coala\s+laundry|lava\s+roupas\s+\d|amaciantes?\s+\d)\b", "", "Cuidado com as roupas", "lavanderia", "lavanderia", "lava roupas", "amaciante"),
    _rule(r"\bpingente\b(?=[\s\S]*\bcopa\s+do\s+brasil\b)", "", "Um símbolo para torcer", "pingente", "pingente", "pingente", "Copa do Brasil"),
    _rule(r"\b(?:microcorrente|massajador\s+facial)\b", "", "Cuidado facial na rotina", "facial", "facial", "facial", "microcorrente"),
    _rule(r"\bfonte\s+de\s+bambu\b", "", "Fonte decorativa de parede", "fonte", "fonte", "fonte", "bambu"),
    _rule(r"\b(?:guarda[- ]?chuva|sombrinha)\b(?=[\s\S]*\b(?:pet|c[aã]es?|gatos?)\b)", "", "Guarda-chuva para pets", "guarda-chuva", "pet", "guarda-chuva", "pets"),
    _rule(r"\b(?:kit\s+papelaria\s+de\s+patas|material\s+escolar\s+kit\s+patinhas)\b", "", "Papelaria com tema de patinhas", "papelaria", "papelaria", "papelaria", "patinhas"),
    _rule(r"\b(?:recheio\s+e\s+cobertura|recheio\s+cobertura)\b", "", "Recheio de morango para receitas", "recheio", "receitas", "recheio", "morango"),
    _rule(r"\b(?:kit\s+4\s+dilatador(?:es)?\s+nasal|dilatador\s+nasal)\b", "", "Dilatador nasal para dormir", "dilatador", "dilatador", "dilatador nasal"),
    _rule(r"\b(?:skate\s+el[eé]trico|scooter\s+acrob[aá]tico)\b", "", "Skate elétrico para brincar", "skate", "skate", "skate elétrico"),
    _rule(r"\bshortsfemininosocialdelinho\b", "", "Short social de linho", "short", "short", "short", "linho"),
    _rule(r"\bpalette\b(?=[\s\S]*\b(?:eudora|niina|secrets|neutrals)\b)", "", "Paleta em tons neutros", "paleta", "paleta", "palette", "neutrals"),
    _rule(r"\b(?:dr\.\s*althea|relief\s+cream|barrier\s+cream)\b", "", "Creme para a pele", "creme", "pele", "cream"),
    _rule(r"\bprote[ií]na\b(?=[\s\S]*\bwhey\b)|\bprotein\s+egg\s+whey\b", "", "Proteína para a rotina", "proteina", "proteina", "whey"),
    _rule(r"\bbabador\b", "", "Babador com bolso coletor", "babador", "babador", "babador", "bolso"),
    _rule(r"\b(?:redmagic\s+\d|uranyx\s+[a-z]\d|realme\s+c\d|redmi\s+note\s+\d)\b", "", "Celular no cotidiano", "celular", "celular", "smartphone"),
    _rule(r"\b(?:mem[oó]ria|memory)\b(?=[\s\S]*\b(?:ddr|ram)\b)", "", "Memória para computador", "memoria", "memoria", "memória", "DDR"),
    _rule(r"\b(?:whey\s+protein|whey\s+isolado|protein\s+egg\s+whey)\b", "", "Whey protein na rotina", "whey", "whey", "whey protein"),
    _rule(r"\b(?:smart\s*band|smartband)\b", "", "Pulseira para a rotina", "pulseira", "pulseira", "smart band"),
    _rule(r"\bmedidor\s+de\s+press[aã]o\s+arterial\b", "", "Medidor de pressão arterial", "medidor", "medidor", "pressão arterial"),
    _rule(r"\b(?:biodance|collagen\s+real\s+deep\s+mask|deep\s+mask)\b", "", "Máscara facial na rotina", "mascara", "mascara", "mask"),
    _rule(r"\b(?:aji[- ]?sal|sal\s+fino)\b", "", "Tempero para o preparo", "tempero", "tempero", "sal fino"),
    _rule(r"\b(?:cabo\s+de\s+carregamento|cabo\s+c\s+usb|cabo\s+usb)\b", "", "Cabo para carregar dispositivos", "cabo", "cabo", "cabo", "carregamento"),
    _rule(r"\b(?:ado[cç]ante|stevia)\b", "", "Adoçante para bebidas e receitas", "adocante", "adocante", "adoçante"),
    _rule(r"\b(?:pap[aá]\s+psitac[ií]deos|pap[aá]\s+para\s+calopsitas?)\b", "", "Alimento para aves", "alimento", "alimento", "papá", "aves"),
    _rule(r"\baditivo\b(?=[\s\S]*\bradiador\b)", "", "Aditivo para o radiador", "aditivo", "aditivo", "aditivo", "radiador"),
    _rule(r"\b(?:timer\s+de\s+ovo|temporizador\s+timer\s+de\s+ovo)\b", "", "Temporizador para ovos", "temporizador", "temporizador", "timer", "ovo"),
    _rule(r"\b(?:armazenamento\s+de\s+cabos|protetora\s+de\s+cabos)\b", "", "Organizador para cabos", "organizador", "organizador", "cabos"),
    _rule(r"\b(?:tennis\s+boys|children's\s+tennis)\b", "", "Tênis infantil casual", "tenis", "tenis", "tennis"),
    _rule(r"\bavental\b", "", "Avental para a rotina", "avental", "avental", "avental"),
    _rule(r"\b(?:climatizador\s+de\s+ar|climatizador)\b", "", "Climatizador para a casa", "climatizador", "climatizador", "climatizador"),
    _rule(r"\b(?:fan\s+de\s+escrit[oó]rio|ventilador\s+port[aá]til)\b", "", "Ventilador para a mesa", "ventilador", "ventilador", "fan"),
    _rule(r"\b(?:gargantilha|colar)\b(?=[\s\S]*\bpingente\b)", "", "Pingente com mensagem especial", "colar", "colar", "pingente"),
    _rule(r"\b(?:retoque\s+de\s+raiz|magic\s+retouch)\b", "", "Retoque de raiz", "retoque", "cabelo", "retoque de raiz"),
    _rule(r"\b(?:flu[ií]do\s+engrossador|finalizador\s+bio\s+extratus|p[oó]s[- ]?qu[ií]mica)\b", "", "Cuidado capilar na rotina", "cabelo", "cabelo", "cabelo"),
    _rule(r"\bscrunchie\b(?=[\s\S]*\bz[ií]per\b)", "", "Scrunchie com bolso discreto", "scrunchie", "scrunchie", "scrunchie", "zíper"),
    _rule(r"\b(?:papai\s+noel|noel)\b(?=[\s\S]*\b(?:m[uú]sica|saxofone|movimentos?)\b)", "", "Papai Noel musical", "natal", "natal", "Papai Noel", "música"),
    _rule(r"\b(?:coberdrom|edredrom|edredom)\b", "", "Coberdrom macio para a cama", "coberdrom", "coberdrom", "coberdrom"),
    _rule(r"\b(?:powerbank|power\s*bank)\b", "", "Bateria extra para dispositivos", "powerbank", "powerbank", "powerbank"),
    _rule(r"\b(?:c[ií]lios\s+posti[cç]os|cluster\s+de\s+c[ií]lios)\b", "", "Cílios para compor o olhar", "cilios", "cilios", "cílios postiços"),
    _rule(r"\b(?:extratora\s+de\s+sujeira|spot\s+cleaner)\b", "", "Limpeza de tecidos e estofados", "extratora", "extratora", "extratora"),
    _rule(r"\b(?:arranjo\s+de\s+orqu[ií]dea|orqu[ií]dea\s+rosa\s+no\s+vidro)\b", "", "Orquídea rosa em arranjo", "orquidea", "orquidea", "orquídea", "arranjo"),
    _rule(r"\bal[cç]a\b(?=[\s\S]*\b(?:sacolas|baldes|latas)\b)", "", "Alça para carregar sacolas", "alca", "alca", "alça", "sacolas"),
    _rule(r"\bmoto\s+el[eé]trica\b", "", "Moto elétrica para passeios", "moto", "moto", "moto elétrica"),
    _rule(r"\bsobretudo\b", "", "Sobretudo de lã forrado", "sobretudo", "sobretudo", "sobretudo", "lã"),
    _rule(r"\b(?:zero\s+pore\s+pad|pore\s+pad)\b", "", "Pads para cuidado facial", "pads", "pele", "pore pad"),
    _rule(r"\b(?:renovadores?\s+faciais|kit\s+dupla\s+renovadores?)\b", "", "Cuidado facial na rotina", "facial", "facial", "renovadores faciais"),
    _rule(r"\b(?:melissa\s+cross|m[- ]?lover\s+platform)\b", "", "Sandália com plataforma", "sandalia", "sandalia", "platform"),
    _rule(r"\b(?:measuring\s+cup|copo\s+medidor|x[ií]cara\s+medidora)\b", "", "Medidas práticas para receitas", "medidor", "medidor", "measuring cup"),
    _rule(r"\b(?:l[aâ]mina\s+sobrancelha|navalhete\s+para\s+depila[cç][aã]o)\b", "", "Lâmina para cuidados faciais", "lamina", "lamina", "lâmina", "sobrancelha"),
    _rule(r"\b(?:ballerine|sapatilha\s+coelho)\b", "", "Toque lúdico no visual", "sapatilha", "sapatilha", "sapatilha", "coelho"),
    _rule(r"\b(?:meleira|colmeira)\b", "", "Meleira de vidro", "meleira", "meleira", "meleira", "vidro"),
    _rule(r"\b(?:hair\s+mask|fino\s+premium\s+touch)\b", "", "Máscara de cuidado capilar", "mascara", "cabelo", "hair mask"),
    _rule(r"\b(?:colher\s+e\s+garfo\s+sobremesa|colher\s+plana\s+dobr[aá]vel)\b", "", "Talheres para servir à mesa", "talher", "talher", "colher", "garfo"),
    _rule(r"\b(?:colher\s+para\s+colocar\s+pate\s+de\s+gato)\b", "", "Colher para servir alimento pet", "colher", "pet", "colher", "gato"),
    _rule(r"\b(?:azeite\s+extra\s+virgem)\b", "", "Azeite para as refeições", "azeite", "azeite", "azeite"),
    _rule(r"\b(?:fogareiro\s+el[eé]trico)\b", "", "Fogareiro para a cozinha", "fogareiro", "fogareiro", "fogareiro"),
    _rule(r"\b(?:cal[cç]olinha|calcinha\s+juvenil)\b", "", "Calcinha juvenil de algodão", "calcinha", "calcinha", "calcinha", "algodão"),
    _rule(r"\b(?:casa\s+casinha\s+cachorros?|casa\s+para\s+cachorros?)\b", "", "Casinha para pets", "casinha", "pet", "casinha", "pets"),
    _rule(r"\bconjunto\b(?=[\s\S]*\bfitness\b)", "", "Conjunto para treino", "conjunto", "fitness", "conjunto", "fitness"),
    _rule(r"\b(?:kit\s+3\s+reparador\s+pontas|reparador\s+pontas\s+cabelos\s+cacheados)\b", "", "Cuidado para as pontas", "cuidado", "cabelo", "pontas", "cabelos cacheados"),
    _rule(r"\bsupreme\s+oil\b", "", "Óleo para os fios", "oleo", "cabelo", "óleo", "fios"),
    _rule(r"\b(?:par\s+de\s+alian[cç]as|alian[cç]as)\b(?=[\s\S]*\btungst[eê]nio\b)", "", "Alianças de tungstênio", "alianca", "alianca", "alianças", "tungstênio"),
    _rule(r"\b(?:lego\s+editions\s+trof[eé]u|trof[eé]u\s+oficial\s+da\s+copa\s+do\s+mundo)\b", "", "Troféu para montar", "trofeu", "trofeu", "troféu", "montar"),
    _rule(r"\b(?:creme\s+para\s+a\s+pele|capsule\s+cream|barrier\s+cream|relief\s+cream|cream)\b", "", "Creme para a pele", "creme", "pele", "cream"),
    _rule(r"\b(?:smart\s*band|smartband)\b", "", "Pulseira para a rotina", "pulseira", "pulseira", "smart band"),
    _rule(r"\b(?:fino\s+premium\s+touch|hair\s+mask)\b", "", "Máscara capilar na rotina", "mascara", "cabelo", "hair mask"),
    _rule(r"\b(?:kit\s+pia\s+completo|kit\s+pia)\b", "", "Itens para a pia", "pia", "pia", "pia"),
    _rule(r"\b(?:kit\s+dupla\s+renovadores?\s+faciais|renovadores?\s+faciais)\b", "", "Cuidado facial na rotina", "facial", "facial", "renovadores faciais"),
    _rule(r"\b(?:lata\s+de\s+lixo|lixeira)\b(?=[\s\S]*\b(?:troca\s+autom[aá]tica|autom[aá]tica)\b)", "", "Lixeira com abertura automática", "lixeira", "lixeira", "lixeira", "automática"),
    _rule(r"\b(?:medidor\s+de\s+press[aã]o\s+arterial|esfigmoman[oô]metro)\b", "", "Medidor de pressão arterial", "medidor", "medidor", "pressão arterial"),
    _rule(r"\b(?:arvore\s+de\s+natal|christmas\s+tree)\b", "", "Árvore de Natal decorativa", "arvore", "natal", "árvore de natal"),
    _rule(r"\b(?:scooter\s+toy|scooter\s+rotativo|patinete\s+el[eé]trico)\b", "", "Brinquedo para passeios", "brinquedo", "brinquedo", "scooter"),
    _rule(r"\b(?:melatonina\s+em\s+gummys?|gummys?\s+de\s+melatonina)\b", "", "Gomas de melatonina", "gomas", "gomas", "melatonina"),
    _rule(r"\b(?:tosquiadeira|aparador)\b(?=[\s\S]*\b(?:animais|pets?|estima[cç][aã]o)\b)", "", "Tosquiadeira para pets", "tosquiadeira", "pet", "tosquiadeira", "pets"),
    _rule(r"\b(?:batons?\s+foscos?|conjunto\s+de\s+batons?)\b", "", "Batons foscos em conjunto", "batom", "batom", "batons", "foscos"),
    _rule(r"\b(?:blister\s+ovo\s+de\s+p[aá]scoa)\b", "", "Doce em preparo", "confeitaria", "confeitaria", "blister", "choco"),
    _rule(r"\b(?:ovo\s+de\s+p[aá]scoa|cacau\s+show\s+p[aá]scoa)\b", "", "Uma surpresa especial", "doce", "doce", "ovo de páscoa"),
    _rule(r"\b(?:capa\s+para\s+xiaomi|case\s+elvev|case\s+para\s+xiaomi)\b", "", "Capa para celular", "capa", "capa", "case", "celular"),
    _rule(r"\b(?:kit\s+de\s+banheiro|kit\s+para\s+banheiro|conjunto\s+para\s+banheiro)\b", "", "Conjunto para o banheiro", "banheiro", "banheiro", "banheiro"),
    _rule(r"\b(?:kit\s+lavabo\s+emerald|aromatizadores?\s+\d+ml)\b", "", "Aromas para o lavabo", "aroma", "aroma", "aromatizador", "lavabo"),
    _rule(r"\b(?:ovo\s+de\s+p[aá]scoa\s+ursinhos|ovo\s+de\s+p[aá]scoa)\b", "", "Uma surpresa especial", "doce", "doce", "ovo de páscoa"),
    _rule(r"\b(?:kit\s+coala\s+laundry|lava\s+roupas\s+\d|amaciantes?\s+\d)\b", "", "Cuidado com as roupas", "lavanderia", "lavanderia", "lava roupas", "amaciante"),
    _rule(r"\b(?:kit\s+2\s+pe[cç]as|kit\s+2\s+pe[cç]as)\b(?=[\s\S]*\bcopa\s+do\s+mundo\b)", "", "Cores para torcer na Copa", "copa", "copa", "Copa do Mundo"),
    _rule(r"\b(?:maca\s+power\s+liso|borabella\s+n[aã]o\s+chore\s+mais)\b", "", "Cuidado capilar na rotina", "cabelo", "cabelo", "cuidado capilar"),
    _rule(r"\b(?:fios\s+de\s+cabelo\s+tinsel|tinsel\s+coloridos?)\b", "", "Fios coloridos para penteados", "cabelo", "cabelo", "fios coloridos"),
    _rule(r"\b(?:natura\s+aura\s+alba|aura\s+alba)\b", "", "Fragrância para rotina", "perfume", "perfume", "aura alba"),
    _rule(r"\b(?:mini\s+melissa\s+hip|melissa\s+hip)\b", "", "Sandália infantil", "sandalia", "sandalia", "Melissa Hip"),
    _rule(r"\b(?:travessa\s+em\s+cristal|travessa\s+de\s+cristal)\b", "", "Travessa de cristal", "travessa", "travessa", "travessa", "cristal"),
    _rule(r"\b(?:restaurador\s+de\s+pl[aá]sticos|pl[aá]sticos\s+do\s+carro)\b", "", "Plásticos do carro em destaque", "carro", "carro", "plásticos", "carro"),
    _rule(r"\b(?:lembran[cç]as?\s+casamento|lembran[cç]as?\s+personalizadas)\b", "", "Lembranças personalizadas", "lembranca", "lembranca", "lembranças"),
    _rule(r"\b(?:alimento\s+para\s+aves|pap[aá]\s+psitac[ií]deos)\b", "", "Alimento para aves", "alimento", "alimento", "aves"),
    _rule(r"\b(?:tinta\s+para\s+cabelo|tonalizante\s+sem\s+am[oô]nia)\b", "", "Cor para os cabelos", "tinta", "cabelo", "tonalizante"),
    _rule(r"\b(?:arvore\s+de\s+natal|christmas\s+tree)\b", "", "Árvore de Natal decorativa", "arvore", "natal", "árvore de natal"),
    _rule(r"\b(?:chocolate\s+de\s+p[aá]scoa|ovo\s+de\s+p[aá]scoa)\b", "", "Uma surpresa especial", "doce", "doce", "ovo de páscoa"),
    _rule(r"\b(?:visual\s+de\s+inverno|moda\s+inverno)\b(?=[\s\S]*\bfeminino\b)", "", "Visual feminino de inverno", "moda", "moda", "inverno"),
    _rule(r"\b(?:capa\s+para\s+xiaomi|case\s+elvev)\b", "", "Capa para celular", "capa", "capa", "case", "celular"),
    _rule(r"\b(?:climatizador\s+de\s+ar|ventilador\s+port[aá]til|fan\s+de\s+escrit[oó]rio)\b", "", "Climatização para a rotina", "climatizacao", "climatizacao", "climatizador"),
    _rule(r"\b(?:cal[cç]olinha|calcinha\s+juvenil)\b", "", "Calcinha juvenil de algodão", "calcinha", "calcinha", "calcinha", "algodão"),
    _rule(r"\b(?:kit\s+2\s+p[eé]ças|kit\s+2\s+pe[cç]as)\b(?=[\s\S]*\b(?:fifa|copa)\b)", "", "Cores para torcer na Copa", "copa", "copa", "Copa"),
    _rule(r"\b(?:kit\s+coala\s+home|coala\s+home\s+ch[aá])\b", "", "Aromas para a casa", "aroma", "aroma", "Coala Home"),
    _rule(r"\b(?:kit\s+2\s+pe[cç]as\s+copa|kit\s+2\s+pe[cç]as)\b", "", "Cores para torcer na Copa", "copa", "copa", "Copa"),
    _rule(r"\b(?:short\s+feminino\s+social|shortsfemininosocial)\b", "", "Short social de linho", "short", "short", "short", "linho"),
    _rule(r"\b(?:blister\s+ovo|ovo\s+de\s+p[aá]scoa\s+ursinhos)\b", "", "Ovo de Páscoa", "ovo", "ovo", "ovo de páscoa"),
    _rule(r"\b(?:polo\s+masculina|kit\s+\d+\s+polo)\b", "", "Polo masculina para a rotina", "polo", "polo", "polo"),
    _rule(r"\b(?:sai\s+everlopad[oa]|saia\s+transpassada)\b", "", "Saia transpassada", "saia", "saia", "saia"),
    _rule(r"\b(?:cobre[- ]?leito|coberdrom)\b", "", "Detalhes para a cama", "cama", "cama", "cama"),
    _rule(r"\b(?:ninhada\s+de\s+cachorro|cachorro\s+de\s+ver[aã]o)\b", "", "Acessório para cães", "pet", "pet", "cães"),
    _rule(r"\b(?:kit\s+costura|mini\s+kit\s+costura)\b", "", "Kit de costura para reparos", "costura", "costura", "costura"),
    _rule(r"\b(?:lata\s+de\s+lixo|lixeira)\b(?=[\s\S]*\b(?:troca\s+autom[aá]tica|autom[aá]tica)\b)", "", "Lixeira com abertura automática", "lixeira", "lixeira", "lixeira", "automática"),
    _rule(r"\b(?:top\s+esportivo|conjunto\s+fitness|conjunto\s+academia)\b", "", "Conjunto para acompanhar o treino", "conjunto", "fitness", "conjunto", "fitness"),
    _rule(r"\b(?:serpentinas?|confetes?)\b", "", "Cores para a festa", "festa", "festa", "serpentinas"),
    _rule(r"\b(?:trava\s+invis[ií]vel|seguran[cç]a\s+para\s+gavetas?)\b", "", "Trava discreta para gavetas", "trava", "trava", "trava", "gavetas"),
    _rule(r"\b(?:ecol[aá]pis|l[aá]pis\s+de\s+cor)\b", "", "Cores para desenhar", "lapis", "lapis", "ecolápis"),
    _rule(r"\b(?:lip\s+oil|brilho\s+labial)\b", "", "Brilho para os lábios", "labios", "labios", "lip oil"),
    _rule(r"\b(?:rice\s+toner|toner)\b", "", "Tônico facial na rotina", "toner", "toner", "toner"),
    _rule(r"\b(?:multiprocessador|power\s+chop)\b", "", "Preparo prático na cozinha", "multiprocessador", "multiprocessador", "multiprocessador"),
    _rule(r"\b(?:capa\s+para\s+xiaomi|case\s+elvev|case\s+para\s+xiaomi)\b", "", "Capa para celular", "capa", "capa", "case", "celular"),
    _rule(r"\b(?:kit\s+de\s+banheiro|kit\s+para\s+banheiro|conjunto\s+para\s+banheiro)\b", "", "Conjunto para o banheiro", "banheiro", "banheiro", "banheiro"),
    _rule(r"\b(?:coala\s+home|coala\s+laundry)\b", "", "Aromas para a casa", "aroma", "aroma", "coala home"),
    _rule(r"\b(?:ovo\s+de\s+p[aá]scoa)\b", "", "Uma surpresa especial", "doce", "doce", "ovo de páscoa"),
    _rule(r"\b(?:petisqueiras?|barquinha\s+c[aâ]noa)\b", "", "Petiscos servidos à mesa", "petisqueira", "petisqueira", "petisqueira"),
    _rule(r"\b(?:roupinhas?\s+e\s+vestidinhos?\s+pet|vestidinhos?\s+pet)\b", "", "Roupa para pets", "roupa", "pet", "roupinhas", "pet"),
    _rule(r"\b(?:polo\s+masculina|polos\s+masculinas?)\b", "", "Polo masculina para a rotina", "polo", "polo", "polo"),
    _rule(r"\b(?:preven[cç][aã]o\s+de\s+estrias|cuidado\s+completo\s+pr[eé])\b", "", "Cuidado na gestação", "pele", "pele", "estrias", "gestação"),
    _rule(r"\b(?:casa\s+casinha\s+cachorros?|casa\s+para\s+cachorros?)\b", "", "Casinha para pets", "casinha", "pet", "casinha", "pets"),
    _rule(r"\ba\s+mulher\s+na\s+su[ií]te\s+\d+\b", "", "Uma leitura para a pausa", "livro", "livro", "leitura"),
    _rule(r"\btoque\s+perolado\s+metalizado\b", "", "Efeito perolado metalizado", "acabamento", "acabamento", "perolado", "metalizado"),
    _rule(r"\bredmagic\s+\d+[a-z]*\b", "", "Celular no cotidiano", "celular", "celular", "redmagic"),
    _rule(r"\buranyx\s+[a-z]\d+\b", "", "Celular no cotidiano", "celular", "celular", "uranyx"),
    _rule(r"\bmem[oó]ria\b(?=[\s\S]*\bddr\s*\d+\b)", "", "Memória para computador", "memoria", "memoria", "memória", "DDR"),
    _rule(r"\bsmart\s*band\b", "", "Rotina acompanhada no pulso", "smartband", "smartband", "smart band"),
    _rule(r"\b(?:leite\s+da\s+vaquinha|tampa\s+leite\s+da\s+vaquinha)\b", "", "Peça flexível para leite", "leite", "leite", "leite", "flexível"),
    _rule(r"\beletrodom[eé]sticos?\s+realistas?\b", "", "Eletrodomésticos para brincar", "brinquedo", "brinquedo", "eletrodomésticos", "realista"),
    _rule(r"\bsuor\b(?=[\s\S]*\bcintura\s+alta\b)(?=[\s\S]*\bfavo\s+de\s+mel\b)", "", "Cintura alta em destaque", "moda", "moda", "cintura alta", "favo de mel"),
    _rule(r"\b(?:collagen\s+night\s+wrapping\s+mask|night\s+wrapping\s+mask)\b", "", "Máscara facial na rotina", "mascara", "mascara", "mask"),
    _rule(r"\b(?:tecla\s+simples|tomada\s+20a)\b(?=[\s\S]*\b(?:tecla|tomada)\b)", "", "Interruptor e tomada", "interruptor", "interruptor", "tomada"),
    _rule(r"\b(?:garra\s+pegador\s+de\s+objetos|pegador\s+de\s+objetos)\b", "", "Garra flexível para objetos", "garra", "garra", "garra", "flexível"),
    _rule(r"\b(?:visual\s+de\s+inverno|moda\s+inverno)\b(?=[\s\S]*\bfeminino\b)", "", "Visual feminino de inverno", "moda", "moda", "inverno"),
    _rule(r"\blorena\s+media\s+duarts\b", "", "Visual para a rotina", "moda", "moda", "visual"),
    _rule(r"\bninhada\s+de\s+cachorro\b", "", "Tema verde militar para pets", "pet", "pet", "cachorro", "verde do exército"),
    _rule(r"\bkit\s+2\s+pe[cç]as\b(?=[\s\S]*\b(?:fifa|copa)\b)", "", "Cores para torcer na Copa", "copa", "copa", "Copa"),
)


# Rules without an explicit `allowed_heads` still need to belong to the
# product named first in the Vision title. These aliases cover genuine parent
# categories while preventing a secondary mention from changing the product
# class (for example, a rubber sole must not turn slippers into erasers).
_CATEGORY_HEAD_ALIASES: dict[str, frozenset[str]] = {
    "arcondicionado": frozenset({"arcondicionado", "climatizador"}),
    "aroma": frozenset({"aromatizador", "difusor", "vela", "incenso", "perfume"}),
    "beleza": frozenset({"maquiagem", "batom", "blush", "gloss", "creme", "serum", "mascara", "protetor", "cilios", "base", "esmalte"}),
    "boneca": frozenset({"boneca", "boneco", "brinquedo", "pelucia"}),
    "cabelo": frozenset({"shampoo", "condicionador", "mascara", "serum", "oleo", "escova", "chapinha", "tintura", "tonalizante", "cabelo"}),
    "chaves": frozenset({"chaveiro", "portachaves"}),
    "cobreleito": frozenset({"cobreleito", "manta", "colcha", "edredom", "coberdrom"}),
    "cozinha": frozenset({
        "airfryer", "fryer", "tostadeira", "cozedor", "panela", "fritadeira",
        "liquidificador", "cafeteira", "mixer", "ralador", "fatiador", "cortador",
        "petisqueira", "pote", "bule", "chaleira", "garrafa", "copo", "caneca",
        "xicara", "taca", "travessa", "colher", "espátula", "talher", "bandeja",
        "fondue", "meleira", "saleiro", "acucareiro", "manteigueira",
    }),
    "copa": frozenset({"short", "camiseta", "conjunto", "cobertor", "bandeira", "meia", "blusa"}),
    "cuidado": frozenset({"creme", "hidratante", "sabonete", "serum", "mascara", "protetor", "shampoo", "condicionador", "depilador", "skincare"}),
    "cuidados": frozenset({"creme", "hidratante", "sabonete", "serum", "mascara", "protetor", "shampoo", "condicionador", "depilador", "skincare"}),
    "doce": frozenset({"pacoca", "chocolate", "doce", "bala", "confeito", "panetone", "ovo", "brigadeiro", "amendoim", "bolo", "bombom"}),
    "facial": frozenset({"mascara", "creme", "serum", "protetor", "skincare", "ampola", "gel"}),
    "leitura": frozenset({"livro", "dicionario", "devocional", "kindle", "leitor"}),
    "moda": frozenset({"blusa", "camiseta", "vestido", "calca", "saia", "short", "conjunto", "tenis", "sapato", "sandalia", "bota", "sapatilha", "scarpin", "cardigan", "casaco", "moletom", "pijama", "calcinha", "sutia", "cinto"}),
    "natal": frozenset({"arvore", "enfeite", "papai", "luminaria", "decoracao"}),
    "papelaria": frozenset({"lapis", "caneta", "caderno", "livro", "estojo", "borracha", "marcatexto", "apontador", "apagador", "cola", "papel", "prancheta", "marcapaginas"}),
    "protetor": frozenset({"protetor", "protetores"}),
    "quebracabeca": frozenset({"quebra", "jogo", "brinquedo", "atividade"}),
    "kit": frozenset({"sabonete", "hidratante", "esfoliante", "desenho", "caneta", "lapis", "copo", "churrasco", "fitness", "conjunto"}),
    "roupas": frozenset({"blusa", "camiseta", "vestido", "calca", "saia", "short", "conjunto", "tenis", "sapato", "sandalia", "bota", "sapatilha", "scarpin", "cardigan", "casaco", "moletom", "pijama", "calcinha", "sutia", "cinto"}),
    "vidro": frozenset({"copo", "jarra", "taca", "bule", "chaleira", "meleira", "travessa", "pote", "vaso"}),
}


def _rule_matches_primary_head(rule: _Rule, heads: set[str]) -> bool:
    if rule.allowed_heads:
        return bool(heads & rule.allowed_heads)
    if not heads:
        # Exact rules for titles with no recognizable product noun remain
        # available; an explicit, different product head blocks them.
        return True
    category = _fold_word(rule.category)
    allowed = _CATEGORY_HEAD_ALIASES.get(category, frozenset({category}))
    return bool(heads & allowed)


def compose_title_rule_caption(context: dict[str, Any]) -> TitleRuleCaption | None:
    title = str(context.get("productName") or "").strip()
    if not title:
        return None
    folded = _fold(title)
    heads = {
        _fold_word(head)
        for head in caption_product_category_terms(title, context)
    }
    accessory_title = bool(re.search(
        r"\b(?:capa|capinha|case|pel[ií]cula|suporte|carregador|adaptador|controle|gamepad|acess[oó]rio)\b",
        folded,
    ))

    airpods_max_device = bool(
        re.search(r"^(?:apple\s+)?airpods\s+max\b", folded)
        and re.search(r"\b(?:usb[- ]?c|bluetooth|cancelamento\s+de\s+ruido|headphone|fone)\b", folded)
    )
    if re.search(r"\bairpods\b", folded) and (not accessory_title or airpods_max_device):
        caption = (
            "Fone com cancelamento de ruído"
            if re.search(r"\bcancelamento\s+de\s+ru[ií]do\b", folded)
            else "Fone com Bluetooth"
        )
        evidence = ("AirPods", "cancelamento de ruído") if "cancelamento" in caption else ("AirPods", "Bluetooth")
        return TitleRuleCaption(
            caption=caption, category="fone", hashtag="fone",
            evidence=evidence,
        )

    if re.search(r"\biphone\b", folded) and not accessory_title and not re.search(
        r"\b(?:gamepad|controle|capa|capinha|case|pel[ií]cula|carregador|adaptador|bot[aã]o)\b",
        folded,
    ):
        return TitleRuleCaption(
            caption="Celular no cotidiano", category="celular",
            hashtag="celular", evidence=("iPhone",),
        )

    if re.search(r"\bipad\b", folded) and not accessory_title:
        return TitleRuleCaption(
            caption="Tablet no cotidiano", category="tablet",
            hashtag="tablet", evidence=("iPad",),
        )

    if re.search(r"\bxiaomi\s+\d{1,2}\s+ultra\b", folded) and not accessory_title:
        return TitleRuleCaption(
            caption="Celular no cotidiano", category="celular",
            hashtag="celular", evidence=("Xiaomi Ultra",),
        )

    if re.search(r"\bnintendo\s+switch\b", folded) and not accessory_title:
        return TitleRuleCaption(
            caption="Console portátil", category="console",
            hashtag="console", evidence=("Nintendo Switch",),
        )

    if re.search(r"\bmarca\s*[-]?\s*texto\b", folded) and re.search(r"\bcores?\b", folded):
        return TitleRuleCaption(
            caption="Marca-texto em várias cores", category="marcatexto",
            hashtag="papelaria", evidence=("marca-texto", "cores"),
        )

    if re.search(r"\b(?:kit\s+de\s+banho|kit\s+banho)\b", folded):
        return TitleRuleCaption(
            caption="Kit para o banho", category="banho",
            hashtag="banho", evidence=("kit de banho",),
        )

    if re.search(r"\b(?:roda\s+gigante|cen[aá]rio)\b.*\bnatal", folded):
        return TitleRuleCaption(
            caption="Roda-gigante natalina", category="decoracao",
            hashtag="natal", evidence=("roda gigante", "natal"),
        )

    if re.search(r"\bmarca\s*[-]?\s*texto\b", folded) and re.search(
        r"\b(?:urso|ursinho)\b", folded,
    ):
        return TitleRuleCaption(
            caption="Marca-texto de ursinho", category="marcatexto",
            hashtag="papelaria", evidence=("marca-texto", "ursinho"),
        )

    if re.search(r"\bphone\s+case\b", folded):
        return TitleRuleCaption(
            caption="Capa para celular", category="capa", hashtag="capa",
            evidence=("phone case", "iphone"),
        )

    if re.search(r"\bbot[aã]o\s+de\s+c[aâ]mera\b", folded) and re.search(
        r"\b(?:iphone|celular|telefone)\b", folded,
    ):
        return TitleRuleCaption(
            caption="Botão de câmera para celular", category="botao", hashtag="botao",
            evidence=("botão de câmera", "iphone"),
        )

    if re.search(r"\b(?:capa|capinha)\b", folded) and re.search(
        r"\b(?:iphone|samsung|celular|telefone)\b", folded,
    ):
        return TitleRuleCaption(
            caption="Capa para celular", category="capa", hashtag="capa",
            evidence=("capa", "celular"),
        )

    if re.search(r"\b(?:banda|pulseira)s?\b", folded) and re.search(
        r"\bapple\s+watch\b", folded,
    ) and re.search(r"\b(?:metal|a[cç]o)\b", folded):
        return TitleRuleCaption(
            caption="Pulseira de metal para relógio", category="pulseira",
            hashtag="pulseira", evidence=("pulseira", "metal", "Apple Watch"),
        )

    # Keep concrete combinations ahead of broad product-family rules below.
    if re.search(r"\blumin[aá]ria\b", folded) and re.search(
        r"\bapontador\b", folded,
    ):
        return TitleRuleCaption(
            caption="Luminária com apontador", category="luminaria",
            hashtag="luminaria", evidence=("luminária", "apontador"),
        )

    if re.search(r"\bsuporte\b", folded) and (not heads or "suporte" in heads) and re.search(
        r"\b(?:celular|telefone)\b", folded,
    ):
        return TitleRuleCaption(
            caption="Suporte para celular", category="suporte",
            hashtag="suporte", evidence=("suporte", "celular"),
        )

    if (not heads or bool(heads & {"arvore", "arvores"})) and re.search(
        r"\barvore\s+de\s+natal\b", folded,
    ) and re.search(
        r"\bmadeira\b", folded,
    ):
        return TitleRuleCaption(
            caption="Árvore de madeira", category="arvore",
            hashtag="natal", evidence=("árvore de natal", "madeira"),
        )

    if re.search(r"\b(?:dji\s+osmo\s+pocket|osmo\s+pocket)\b", folded):
        return TitleRuleCaption(
            caption="Câmera de bolso", category="camera",
            hashtag="camera", evidence=("Osmo Pocket", "câmera"),
        )

    if re.search(r"\b(?:smartphone|celular)\b", folded) and (not heads or bool(heads & {"smartphone", "celular"})) and re.search(
        r"\b(?:super\s+)?amoled\b", folded,
    ):
        return TitleRuleCaption(
            caption="Celular com tela Super AMOLED", category="celular",
            hashtag="celular", evidence=("celular", "Super AMOLED"),
        )

    if re.search(r"\b(?:smartphone|celular)\b", folded) and (not heads or bool(heads & {"smartphone", "celular"})) and re.search(
        r"\b(?:4g|5g)\b", folded,
    ):
        return TitleRuleCaption(
            caption="Smartphone com conexão móvel", category="smartphone",
            hashtag="smartphone", evidence=("smartphone", "5G"),
        )

    if re.search(r"\bal[cç]a\s+flutuante\b", folded) and re.search(
        r"\b(?:celular|c[aâ]mera)\b", folded,
    ):
        target = "celular" if re.search(r"\bcelular\b", folded) else "câmera"
        return TitleRuleCaption(
            caption=f"Alça flutuante para {target}", category="alca",
            hashtag="alca", evidence=("alça flutuante", target),
        )

    if re.search(r"\bcapas?\b", folded) and re.search(
        r"\b(?:protetor\s+solar|bloqueia\s+calor|prote[cç][aã]o\s+solar)\b", folded,
    ) and not re.search(r"\b(?:celular|telefone|iphone|samsung)\b", folded):
        return TitleRuleCaption(
            caption="Capa para bloquear o sol", category="capa",
            hashtag="capa", evidence=("capa", "proteção solar"),
        )

    if re.search(r"\brepelente\b", folded) and re.search(
        r"\b(?:[aá]gua|parabrisa|para[- ]brisa|vidros?)\b", folded,
    ) and not re.search(r"\b(?:mosquito|mosquitos|inseto|insetos|dengue|icaridina)", folded):
        return TitleRuleCaption(
            caption="Proteção contra água no para-brisa", category="repelente",
            hashtag="carro", evidence=("repelente de água", "para-brisa"),
        )

    if re.search(r"\bflanela\b", folded) and (not heads or "flanela" in heads) and re.search(
        r"\b(?:lentes?|[oó]culos|tela|limpar|limpeza)\b", folded,
    ):
        return TitleRuleCaption(
            caption="Flanela para lentes e telas", category="flanela",
            hashtag="flanela", evidence=("flanela", "lentes", "tela"),
        )

    if re.search(r"\bkit\s+desenho\s+infantil\b", folded) and re.search(
        r"\bcolorir\b", folded,
    ):
        return TitleRuleCaption(
            caption="Kit de desenho para colorir", category="kit",
            hashtag="desenho", evidence=("kit desenho", "colorir"),
        )

    if re.search(r"\bkit\s+\d+\s+livro\s+caixa\s+decorativo\b", folded):
        return TitleRuleCaption(
            caption="Caixa decorativa em formato de livro", category="caixa",
            hashtag="decoracao", evidence=("livro caixa", "decorativo"),
        )

    if re.search(r"\bcola\b", folded) and re.search(
        r"\b(?:veda[cç][aã]o|vedar|furo\s+de\s+parede)\b", folded,
    ):
        return TitleRuleCaption(
            caption="Cola para vedação", category="cola",
            hashtag="cola", evidence=("cola", "vedação"),
        )

    if re.search(r"\bkit\b(?=[\s\S]*\bchurrasco\b)(?=[\s\S]*\bcopo\s+t[eé]rmico\b)", folded):
        return TitleRuleCaption(
            caption="Kit para o churrasco", category="kit",
            hashtag="churrasco", evidence=("kit", "churrasco"),
        )

    if re.search(r"\b(?:pet|gato|c[aã]o|cachorro)\b", folded) and re.search(
        r"\b(?:fantasia|traje|cosplay)\b", folded,
    ):
        return TitleRuleCaption(
            caption="Fantasia para pets", category="pet",
            hashtag="pet", evidence=("fantasia", "pet"),
        )

    if re.search(r"\b(?:kit|conjunto)\b", folded) and re.search(
        r"\b(?:banheiro|lavabo)\b", folded,
    ) and re.search(r"\b(?:porta[- ]escova|dispenser|sabonete|escova\s+de\s+dentes)\b", folded) and not (
        re.search(r"\bfrascos?\b", folded)
        and re.search(r"\b(?:shampoo|condicionador)\b", folded)
        and not re.search(r"\b(?:dispenser|porta[- ]escova|escova\s+de\s+dentes)\b", folded)
    ):
        if re.search(r"\bvidro\b", folded) and re.search(r"\bambar\b", folded):
            caption, evidence = "Conjunto de banheiro em vidro âmbar", ("banheiro", "vidro", "âmbar")
        else:
            caption, evidence = "Conjunto para o banheiro", ("banheiro", "conjunto")
        return TitleRuleCaption(
            caption=caption, category="banheiro", hashtag="banheiro",
            evidence=evidence,
        )

    if re.search(r"\bbast[aã]o\b", folded) and re.search(
        r"\bresfriador\b", folded,
    ):
        return TitleRuleCaption(
            caption="Bastão resfriador para cerveja", category="bastao",
            hashtag="cerveja", evidence=("bastão", "resfriador", "cerveja"),
        )

    if re.search(r"\b(?:air\s*fryer|fritadeira\s+air\s*fryer)\b", folded) and not re.search(
        r"\b(?:capa|protetor|forro|tapete|papel|acess[oó]rio|forma)\b", folded,
    ):
        return TitleRuleCaption(
            caption="Preparo na air fryer", category="airfryer",
            hashtag="airfryer", evidence=("air fryer",),
        )

    if re.search(r"\bcobre[- ]?leito\b", folded):
        if re.search(r"\bpercal\b", folded):
            caption, evidence = "Cobre-leito em percal", ("cobre-leito", "percal")
        elif re.search(r"\bcanelad[oa]\b", folded):
            caption, evidence = "Cobre-leito canelado", ("cobre-leito", "canelado")
        elif re.search(r"\bmicrofibra\b", folded):
            caption, evidence = "Cobre-leito de microfibra", ("cobre-leito", "microfibra")
        elif re.search(r"\bdupla\s+face\b", folded):
            caption, evidence = "Cobre-leito dupla face", ("cobre-leito", "dupla face")
        else:
            caption, evidence = "Cobre-leito para a cama", ("cobre-leito",)
        return TitleRuleCaption(
            caption=caption, category="cobreleito", hashtag="cobreleito",
            evidence=evidence,
        )

    if re.search(r"\bpel[ií]cula\b", folded) and re.search(
        r"\b(?:iphone|samsung|celular|telefone)\b", folded,
    ):
        return TitleRuleCaption(
            caption="Película para celular", category="pelicula", hashtag="pelicula",
            evidence=("película", "celular"),
        )

    if re.search(r"\bcarregador\b", folded) and re.search(
        r"\b(?:iphone|celular|telefone)\b", folded,
    ):
        return TitleRuleCaption(
            caption="Carregador para celular", category="carregador", hashtag="carregador",
            evidence=("carregador", "iphone"),
        )

    if re.search(r"\bcushion\b", folded) and re.search(r"\bmatte\b", folded):
        return TitleRuleCaption(
            caption="Base cushion com acabamento matte",
            category="maquiagem",
            hashtag="maquiagem",
            evidence=("cushion", "matte"),
        )

    if re.search(r"\bguarda[- ]roupa\b", folded):
        if re.search(r"\bportas?\s+de\s+correr\b", folded):
            caption = "Guarda-roupa com portas de correr"
        elif re.search(r"\bsolteiro\b", folded):
            caption = "Guarda-roupa de solteiro"
        else:
            caption = "Guarda-roupa para quarto"
        return TitleRuleCaption(caption, "roupa", "roupa", ("guarda-roupa",))

    if re.search(r"\bjogo\b.*\bfutebol\b.*\bmesa\b", folded):
        return TitleRuleCaption(
            "Futebol de mesa", "futebol", "futebol", ("futebol", "mesa"),
        )

    for rule in _RULES:
        if not rule.pattern.search(folded):
            continue
        # Shampoo/conditioner keywords also appear in listings for empty
        # travel bottles. In those titles the products sold are containers,
        # so the paired-product caption would be a semantic false positive.
        if rule.caption == "Shampoo e condicionador" and (
            re.search(
                r"\b(?:dispenser|vazio|embalagem|acessorios de viagem|frasco dividido)\b",
                folded,
            )
            or re.search(r"\bkit banheiro\b.*\bfrascos?\b", folded)
        ):
            continue
        if not _rule_matches_primary_head(rule, heads):
            continue
        return TitleRuleCaption(
            caption=rule.caption,
            category=rule.category,
            hashtag=rule.hashtag,
            evidence=rule.evidence,
        )
    if re.search(r"\bcintura\s+alta\b", folded):
        supported_heads = {
            "calca", "jeans", "saia", "saias", "short", "shorts",
            "shortinho", "shortinhos", "legging", "leggings",
            "jardineira", "jardineiras", "calcinha", "calcinhas", "calcas",
        }
        category = (
            "conjunto"
            if re.search(r"\bconjunto\b", folded)
            else next((head for head in heads if head in supported_heads), None)
        )
        if category:
            hashtag = {
                "saias": "saia",
                "shorts": "short",
                "shortinhos": "shortinho",
                "leggings": "legging",
                "jardineiras": "jardineira",
                "calcinhas": "calcinha",
                "calcas": "calca",
            }.get(category, category)
            caption = {
                "saia": "Saia de cintura alta",
                "saias": "Saia de cintura alta",
                "calca": "Calça de cintura alta",
                "calcas": "Calça de cintura alta",
                "jeans": "Jeans de cintura alta",
                "short": "Short de cintura alta",
                "shorts": "Short de cintura alta",
                "shortinho": "Shortinho de cintura alta",
                "shortinhos": "Shortinho de cintura alta",
                "legging": "Legging de cintura alta",
                "leggings": "Legging de cintura alta",
                "jardineira": "Jardineira de cintura alta",
                "jardineiras": "Jardineira de cintura alta",
                "calcinha": "Calcinha de cintura alta",
                "calcinhas": "Calcinha de cintura alta",
                "conjunto": "Conjunto de cintura alta",
            }.get(category, "Modelagem de cintura alta")
            return TitleRuleCaption(
                caption=caption,
                category=category,
                hashtag=hashtag,
                evidence=("cintura alta",),
            )
    return _compose_product_detail_caption(context, title, folded)


def _compose_product_detail_caption(
    context: dict[str, Any], title: str, folded_title: str,
) -> TitleRuleCaption | None:
    """Pair a recognized product noun with one literal, useful title detail.

    This gives the local generator the concise catalog style used by the
    approved examples (product + one concrete detail), without a model or a
    hand-written rule for every complete title.
    """
    # Marketplace titles for containers often contain the words shampoo and
    # conditioner as intended use. Do not label the container as the liquids.
    if re.search(r"\b(?:frasco|frascos|dispenser|dispensador)\b", folded_title) and re.search(
        r"\b(?:shampoo|condicionador)\b", folded_title,
    ):
        return None

    categories = caption_product_category_terms(title, context)
    if not categories:
        return None
    category = categories[0]
    head = _display_title_head(title, category)
    if not head:
        return None

    if category == "geladeira" and re.search(r"\bduplex\b", folded_title):
        return TitleRuleCaption(
            caption="Geladeira duplex", category=category, hashtag=category,
            evidence=("duplex",),
        )

    if category == "marcatexto" and re.search(r"\b(?:marca\s*texto|marcatexto)\b", folded_title) and re.search(
        r"\b(?:urso|ursinho)\b", folded_title,
    ):
        return TitleRuleCaption(
            caption="Marca-texto de ursinho", category=category, hashtag="papelaria",
            evidence=("marca-texto", "ursinho"),
        )

    if category == "cesta" and re.search(r"\bpalha\b", folded_title):
        return TitleRuleCaption(
            caption="Cesta de palha", category=category, hashtag=category,
            evidence=("palha",),
        )

    if category == "chaveiro" and re.search(r"\bdia\s+das\s+m[aã]es\b", folded_title):
        return TitleRuleCaption(
            caption="Um chaveiro para mães", category=category,
            hashtag=category, evidence=("Dia das Mães",),
        )

    if category == "caderno" and re.search(r"\bde\s+disco\b", folded_title):
        return TitleRuleCaption(
            caption="Caderno de disco", category=category, hashtag=category,
            evidence=("disco",),
        )

    if category == "casaco" and re.search(r"\bl[aã]\s+batida\b", folded_title):
        return TitleRuleCaption(
            caption="Casaco de lã batida", category=category, hashtag=category,
            evidence=("lã batida",),
        )

    if category == "mochila" and re.search(r"\bimperme[aá]vel\b", folded_title):
        return TitleRuleCaption(
            caption="Mochila impermeável", category=category, hashtag=category,
            evidence=("impermeável",),
        )

    if category == "macacao" and re.search(r"\bestampa\b", folded_title):
        return TitleRuleCaption(
            caption="Macacão estampado", category=category, hashtag=category,
            evidence=("estampa",),
        )

    if category in {"lustre", "luminaria"} and re.search(r"\b(?:ramo|galho)\b", folded_title):
        return TitleRuleCaption(
            caption="Luminária em formato de galho", category=category,
            hashtag=category, evidence=("ramo", "galho"),
        )

    if category == "calca" and re.search(r"\b(?:treino|academia|fitness)\b", folded_title):
        return TitleRuleCaption(
            caption="Calça para academia", category=category, hashtag=category,
            evidence=("academia", "treino"),
        )

    if category == "bota" and re.search(r"\bsalto\s+m[eé]dio(?:tratorada)?\b", folded_title):
        return TitleRuleCaption(
            caption="Bota de salto médio", category=category, hashtag=category,
            evidence=("salto médio",),
        )

    if category == "adaptador" and re.search(r"\b(?:rog\s+ally|steam\s+deck|switch)\b", folded_title):
        return TitleRuleCaption(
            caption="Adaptador USB-C", category=category, hashtag=category,
            evidence=("USB-C",),
        )

    if category == "balcao" and re.search(r"\bcooktop\b", folded_title):
        return TitleRuleCaption(
            caption="Balcão para cooktop", category=category, hashtag=category,
            evidence=("cooktop",),
        )

    if category == "bandeira" and re.search(r"\bdupla\s+face\b", folded_title):
        return TitleRuleCaption(
            caption="Bandeira dupla face", category=category, hashtag=category,
            evidence=("dupla face",),
        )

    if re.search(r"\b(?:camiseta|amiseta)\b.*\bbrasil\b.*\bestampa\b.*\bbandeira\b", folded_title):
        return TitleRuleCaption(
            caption="Camiseta com estampa do Brasil", category="camiseta",
            hashtag="camiseta", evidence=("Brasil", "estampa da bandeira"),
        )

    if category == "bolsa" and re.search(r"\bcopo\s*t[eé]rmico|garrafa\s+t[eé]rmica\b", folded_title):
        return TitleRuleCaption(
            caption="Bolsa para copo térmico", category=category, hashtag=category,
            evidence=("copo térmico", "garrafa térmica"),
        )

    if category in {"caneca", "copo", "xicara", "xicaras"} and re.search(
        r"\bcaf[eé]\b", folded_title,
    ):
        return TitleRuleCaption(
            caption="Café quentinho",
            category=category,
            hashtag="cafe",
            evidence=("café",),
        )

    if category == "po" and re.search(r"\bunhas?\b", folded_title):
        return TitleRuleCaption(
            caption="Pó para unhas",
            category=category,
            hashtag="unhas",
            evidence=("pó", "unhas"),
        )

    if category == "suporte" and re.search(r"\b(?:telefone|celular)\b", folded_title):
        return TitleRuleCaption(
            caption="Suporte para celular",
            category=category,
            hashtag=category,
            evidence=("telefone",),
        )

    if category == "suporte" and re.search(r"\b(?:dispenser|suporte)\b", folded_title) and re.search(
        r"\b(?:sab[aã]o|sabonete)\b", folded_title,
    ):
        return TitleRuleCaption(
            caption="Suporte para sabonete",
            category=category,
            hashtag=category,
            evidence=("sabonete", "sabão"),
        )

    if category == "mascara" and re.search(r"\bc[ií]lios\b", folded_title):
        return TitleRuleCaption(
            caption="Máscara para cílios",
            category=category,
            hashtag=category,
            evidence=("cílios",),
        )

    if category == "tv" and re.search(r"\b(?:4k|uhd)\b", folded_title):
        head_text = "Smart TV" if re.search(r"\bsmart\s+tv\b", folded_title) else "TV"
        detail = (
            f"{head_text} UHD"
            if re.search(r"\buhd\b", folded_title)
            else f"{head_text} com alta resolução"
        )
        return TitleRuleCaption(
            caption=detail, category=category, hashtag=category,
            evidence=("uhd" if " UHD" in detail else "4k",),
        )

    if category in {"smartphone", "celular", "tablet"} and re.search(
        r"\b(?:4g|5g)\b", folded_title,
    ) and not re.search(r"\b(?:super\s+)?amoled\b|\boled\b", folded_title):
        head_text = "Smartphone" if category == "smartphone" else _display_title_head(title, category)
        if head_text:
            return TitleRuleCaption(
                caption=f"{head_text} com conexão móvel",
                category=category,
                hashtag=category,
                evidence=("conexão 4G" if re.search(r"\b4g\b", folded_title) else "conexão 5G",),
            )

    if category in {
        "blusa", "camisa", "camiseta", "kimono", "vestido", "moletom",
    } and re.search(r"\bmanga\s+3\s*/\s*4\b", folded_title):
        return TitleRuleCaption(
            caption=f"{_display_title_head(title, category)} de manga média",
            category=category,
            hashtag=category,
            evidence=("manga 3/4",),
        )

    if category == "presilha" and re.search(r"\bsacos?\b", folded_title):
        return TitleRuleCaption(
            caption="Presilha para sacos",
            category=category,
            hashtag=category,
            evidence=("sacos",),
        )

    if category == "gamepad" and re.search(r"\b(?:iphone|android|celular)\b", folded_title):
        return TitleRuleCaption(
            caption="Gamepad para celular",
            category=category,
            hashtag=category,
            evidence=("iphone", "android", "celular"),
        )

    if category == "skincare" and re.search(r"\bskin\s*care\b", folded_title):
        return TitleRuleCaption(
            caption="Cuidados com a pele",
            category=category,
            hashtag="beleza",
            evidence=("skin care",),
        )

    if category == "blusa" and re.search(r"\bde\s+frio\b", folded_title):
        if re.search(r"\bb[aá]sic[ao]\b", folded_title):
            return TitleRuleCaption(
                caption="Blusa básica",
                category=category,
                hashtag=category,
                evidence=("básica",),
            )
        if re.search(r"\bcanguru\b", folded_title):
            return TitleRuleCaption(
                caption="Blusa com bolso canguru",
                category=category,
                hashtag=category,
                evidence=("canguru",),
            )

    if category == "short" and re.search(r"\bshort\s+saia\b", folded_title):
        if re.search(r"\balfaiataria\b", folded_title):
            return TitleRuleCaption(
                "Short-saia de alfaiataria", category, category,
                ("short saia", "alfaiataria"),
            )

    if category == "gloss" and not re.search(r"\b(?:case|capa)\b.*\biphone\b", folded_title):
        return TitleRuleCaption(
            "Gloss labial", category, category, ("gloss",),
        )

    if category == "capa":
        if re.search(r"\b(?:iphone|celular|telefone)\b", folded_title):
            return TitleRuleCaption(
                caption="Capa para celular",
                category=category,
                hashtag=category,
                evidence=("celular", "telefone", "iphone"),
            )
        if re.search(r"\bsof[aá]\b", folded_title):
            return TitleRuleCaption(
                caption="Capa de sofá",
                category=category,
                hashtag=category,
                evidence=("sofá",),
            )
        if re.search(r"\bcolch[aã]o\b", folded_title):
            return TitleRuleCaption(
                caption="Capa para colchão",
                category=category,
                hashtag=category,
                evidence=("colchão",),
            )

    if category == "desodorante" and re.search(r"\bcol[oô]nia\b", folded_title):
        return TitleRuleCaption(
            caption="Desodorante colônia",
            category=category,
            hashtag=category,
            evidence=("colônia",),
        )

    if category == "smartwatch" and re.search(
        r"\bresist[eê]ncia\s+[àa]\s+[áa]gua\b", folded_title,
    ):
        return TitleRuleCaption(
            caption="Smartwatch com resistência à água",
            category=category,
            hashtag=category,
            evidence=("resistência à água",),
        )

    if category == "pa" and re.search(r"\ba[cç]o\s+inoxid[aá]vel\b", folded_title):
        return TitleRuleCaption(
            caption="Pá de aço inoxidável",
            category=category,
            hashtag="jardinagem" if re.search(r"\bjardim\b", folded_title) else category,
            evidence=("aço inoxidável",),
        )

    # Import lazily because grounded.py imports this module inside its
    # candidate-composition function.
    from .grounded import _normalize_vision_fact, extract_vision_caption_facts

    for raw_fact in extract_vision_caption_facts(context, limit=10):
        if not title_fact_is_attached_to_product(title, category, raw_fact):
            continue
        if category == "oculos" and _fold(raw_fact) == "ajustavel":
            # The title may attach this adjective to a lens or an ear
            # protector, so it is not safe to call the glasses adjustable.
            continue
        if category in {"relogio", "smartwatch"} and "digital" in _fold(raw_fact):
            return TitleRuleCaption(
                caption=f"{head} digital",
                category=category,
                hashtag=category,
                evidence=(raw_fact,),
            )
        direct = _compose_category_head_fact(raw_fact, category, _normalize_vision_fact)
        if direct:
            return TitleRuleCaption(
                caption=direct,
                category=category,
                hashtag=category,
                evidence=(raw_fact,),
            )
        detail = _render_title_detail(raw_fact, category)
        if detail is None:
            continue
        detail = _agree_detail_with_head(head, detail)
        return TitleRuleCaption(
            caption=f"{head} {detail}",
            category=category,
            hashtag=category,
            evidence=(raw_fact,),
        )

    # Vision's historical records often preserve only the seller's product
    # title. If no known fact extractor matched, use a short grammatical
    # relation or an unambiguous adjective that appears directly after the
    # product head. This is a reusable title parser, not a per-product caption
    # list; it never keeps IDs, measurements, brand-like tokens, or sales copy.
    title_phrase = _compose_title_head_phrase(title, category, head)
    if title_phrase:
        hashtag = (
            "saidadepraia"
            if category == "saida" and re.search(r"\bsaida\s+de\s+praia\b", folded_title)
            else category
        )
        return TitleRuleCaption(
            caption=title_phrase,
            category=category,
            hashtag=hashtag,
            evidence=(title_phrase,),
        )

    gender = next(
        (value for value in ("masculino", "feminino", "unissex") if re.search(rf"\b{value}\b", folded_title)),
        None,
    )
    if gender and category in {
        "tenis", "sandalia", "sapato", "chinelo", "bota", "sapatilha",
        "vestido", "calca", "calca", "camiseta", "pijama", "perfume",
        "relogio", "bolsa", "jaqueta", "blusa", "sutia", "calcinha",
    }:
        return TitleRuleCaption(
            caption=f"{head} {gender}", category=category, hashtag=category,
            evidence=(gender,),
        )
    return None


_TITLE_RELATION_WORDS = {
    "de", "do", "da", "dos", "das", "com", "para", "em",
}
_TITLE_PHRASE_NOISE = {
    "kit", "feminino", "feminina", "masculino", "masculina", "unissex",
    "adulto", "adulta", "infantil", "juvenil", "original", "importado",
    "atacado", "varejo", "oferta", "promocao", "promocional", "frete",
    "gratis", "grátis", "escolha", "sua", "seu", "modelo",
    "privadinha", "ultra", "colecao", "conforto", "presente", "frio",
    "loja", "mimo", "linha",
}
_TITLE_PHRASE_SKIP_BEFORE_DETAIL = {"ferro", "madeira", "aco", "aço"}
_TITLE_PHRASE_ADJECTIVES = {
    "articulado": "articulado", "articulada": "articulada",
    "automotivo": "automotivo", "automotiva": "automotiva",
    "automatico": "automático", "automatica": "automática",
    "antiaderente": "antiaderente", "antiderrapante": "antiderrapante",
    "autolimpante": "autolimpante", "decorado": "decorado", "decorada": "decorada",
    "dobravel": "dobrável", "eletrico": "elétrico", "eletrica": "elétrica",
    "flexivel": "flexível", "giratorio": "giratório", "giratoria": "giratória",
    "hermetico": "hermético", "hermetica": "hermética",
    "higienico": "higiênico", "higienica": "higiênica",
    "impermeavel": "impermeável", "magnetico": "magnético", "magnetica": "magnética",
    "multifuncional": "multifuncional", "musical": "musical",
    "peludo": "peludo", "peluda": "peluda", "peluciada": "peluciada",
    "portatil": "portátil", "protetora": "protetora",
    "protetor": "protetor", "recarregavel": "recarregável",
    "quadrada": "quadrada", "quadrado": "quadrado", "redondo": "redondo",
    "redonda": "redonda", "regulavel": "regulável", "giratória": "giratória",
    "secadora": "secadora",
    "antiaderentes": "antiaderentes", "antiderrapantes": "antiderrapantes",
    "peludos": "peludos", "peludas": "peludas", "regulaveis": "reguláveis",
    "termico": "térmico", "termica": "térmica", "transparente": "transparente",
    "flexiveis": "flexíveis", "portateis": "portáteis", "redondos": "redondos",
    "redondas": "redondas", "eletricos": "elétricos", "eletricas": "elétricas",
    "hermeticos": "herméticos", "hermeticas": "herméticas",
    "capilar": "capilar", "labial": "labial", "facial": "facial",
    "corporal": "corporal", "lombar": "lombar", "gamer": "gamer",
    "liquido": "líquido", "liquida": "líquida", "longo": "longo",
    "longos": "longos", "longa": "longa", "longas": "longas",
    "curto": "curto", "curta": "curta", "curtos": "curtos", "curtas": "curtas",
    "liso": "liso", "lisa": "lisa", "lisos": "lisos", "lisas": "lisas",
    "estampado": "estampado", "estampada": "estampada",
    "xadrez": "xadrez", "floral": "floral", "canelado": "canelado",
    "canelada": "canelada", "interativo": "interativo", "interativa": "interativa",
    "educativo": "educativo", "educativa": "educativa", "inteligente": "inteligente",
    "inflavel": "inflável", "instantaneo": "instantâneo", "instantanea": "instantânea",
    "organico": "orgânico", "organica": "orgânica", "ortopedico": "ortopédico",
    "ortopedica": "ortopédica", "anatomico": "anatômico", "anatomica": "anatômica",
    "solar": "solar", "elastico": "elástico", "elastica": "elástica",
    "moderno": "moderno", "moderna": "moderna", "retro": "retrô",
    "suspenso": "suspenso", "suspensa": "suspensa", "colorido": "colorido",
    "colorida": "colorida", "personalizado": "personalizado",
    "personalizada": "personalizada", "redondas": "redondas",
    "esportivo": "esportivo", "esportiva": "esportiva", "confortavel": "confortável",
    "confortaveis": "confortáveis", "arabe": "árabe",
    "profissional": "profissional", "rasteira": "rasteira", "rasteirinha": "rasteirinha",
    "rasteiro": "rasteiro", "brilhante": "brilhante",
    "brilhantes": "brilhantes", "emborrachado": "emborrachado",
    "emborrachada": "emborrachada", "volumoso": "volumoso", "volumosa": "volumosa",
    "basico": "básico", "basica": "básica", "basic": "básica",
    "multiuso": "multiuso", "hidrografica": "hidrográfica",
    "pantalona": "pantalona", "colegial": "colegial", "media": "média",
    "medio": "médio", "universal": "universal", "aramado": "aramado",
    "plissado": "plissado", "plissada": "plissada", "listrado": "listrado",
    "listrada": "listrada",
    "peluciado": "peluciado", "felpudo": "felpudo", "felpuda": "felpuda",
    "ondulado": "ondulado", "ondulada": "ondulada", "estofado": "estofado",
    "estofada": "estofada", "aberto": "aberto", "aberta": "aberta",
    "elasticos": "elásticos",
    "elasticas": "elásticas", "empilhavel": "empilhável", "duplo": "duplo",
    "dupla": "dupla", "depilatorio": "depilatório", "depilatoria": "depilatória",
    "aberto": "aberto", "aberta": "aberta", "escamoteavel": "escamoteável",
    "fosco": "fosco", "fosca": "fosca", "decorativa": "decorativa",
    "americano": "americano", "americana": "americana", "brochura": "brochura",
    "dura": "dura",
    "eletronico": "eletrônico", "eletronica": "eletrônica",
    "preto": "preto", "preta": "preta", "branco": "branco", "branca": "branca",
    "azul": "azul", "vermelho": "vermelho", "vermelha": "vermelha",
    "rosa": "rosa", "dourado": "dourado", "dourada": "dourada",
    "prateado": "prateado", "prateada": "prateada", "cinza": "cinza",
}

_TITLE_PHRASE_DETAIL_RELATIONS = {
    "pet": "para pet", "gato": "para gatos", "gatos": "para gatos",
    "cachorro": "para cachorro", "cachorros": "para cachorros",
    "percal": "de percal", "glicerina": "de glicerina",
    "led": "de LED", "leds": "de LED", "pvc": "de PVC",
    "inox": "em inox", "unhas": "para unhas", "celular": "para celular",
    "telefone": "para telefone", "cafe": "para café", "cha": "para chá",
    "inverno": "de inverno", "natal": "de Natal", "marmore": "de mármore",
    "algodao": "de algodão", "silicone": "de silicone", "madeira": "de madeira",
    "papete": "papete", "marca-texto": "marca-texto", "marcatexto": "marca-texto",
    "labio": "labial", "labios": "labial", "cintura": "de cintura alta",
    "esportivo": "esportivo", "esportiva": "esportiva", "bolso": "com bolso",
    "bolsos": "com bolsos", "pauta": "com pauta", "brilho": "com brilho",
    "canudo": "com canudo", "pelucia": "de pelúcia",
    "vinil": "de vinil", "inox": "em inox", "wifi": "com Wi-Fi",
    "torx": "Torx", "bambu": "de bambu", "bebe": "para bebê",
    "sala": "para sala", "quarto": "para quarto", "cozinha": "para cozinha",
    "banheiro": "para banheiro", "viagem": "de viagem", "pocket": "de bolso",
    "masculino": "masculino", "feminino": "feminino", "esporte": "esportivo",
    "sabonete": "para sabonete", "sabao": "para sabão", "geladeira": "para geladeira",
    "safari": "safari", "casal": "para casal", "maternidade": "para maternidade",
    "jeans": "jeans", "rasteira": "rasteira", "rasteirinha": "rasteirinha",
    "posta": "posta", "banhao": "de banho", "carrinho": "para carrinhos",
    "linho": "de linho", "arabica": "arábica", "prata": "de prata",
    "ceramica": "de cerâmica", "melancia": "de melancia", "limpeza": "de limpeza",
    "jantar": "de jantar", "banho": "de banho", "jardim": "para jardim",
    "livros": "para livros", "livro": "para livros", "ferrugem": "para ferrugem",
    "cachorros": "para cachorros", "caes": "para cães", "cães": "para cães",
    "latas": "para latas", "freezer": "para freezer", "garagem": "para garagem",
    "cabelo": "para cabelo", "sobrancelha": "para sobrancelha",
    "casamento": "para casamento", "piso": "para o piso", "cerveja": "para cerveja",
}
_TITLE_PHRASE_FEATURES = {
    ("manga", "longa"): "de manga longa",
    ("manga", "curta"): "de manga curta",
    ("bico", "fino"): "de bico fino",
    ("cano", "alto"): "de cano alto",
    ("cano", "medio"): "de cano médio",
    ("meia", "lua"): "meia-lua",
    ("gola", "alta"): "com gola alta",
    ("corpo", "inteiro"): "de corpo inteiro",
    ("sola", "alta"): "de sola alta",
    ("camera", "dupla"): "com câmera dupla",
    ("camera", "tripla"): "com câmera tripla",
    ("com", "pauta"): "com pauta",
    ("tela", "super", "amoled"): "com tela Super AMOLED",
    ("dupla", "face"): "dupla face",
    ("controle", "de", "torque"): "com controle de torque",
    ("resistencia", "a", "agua"): "com resistência à água",
    ("marca", "texto"): "marca-texto",
    ("copo", "de", "vidro"): "com copo de vidro",
}
_TITLE_COMPOUND_PRODUCT_PAIRS = {
    ("parafusadeira", "furadeira"): "e",
    ("furadeira", "parafusadeira"): "e",
}
_TITLE_RELATION_PRODUCT_OBJECTS = {
    "sofa", "painel", "celular", "telefone", "cabeceira", "mesa",
    "cafe", "cha", "unha", "unhas", "cachorro", "cachorros", "gato",
    "gatos", "cozinha", "banheiro", "carro", "moto", "praia", "jardim",
    "sala", "quarto", "parede", "roupa", "cabelo", "frio", "inverno",
    "colchao", "cama", "portao", "janela",
}
_TITLE_SYNONYM_HEADS = {
    "capa": {"capinha", "case", "protetor"},
    "celular": {"smartphone", "iphone"},
    "smartphone": {"celular", "iphone"},
    "relogio": {"smartwatch", "watch"},
    "smartwatch": {"relogio", "watch"},
    "sandalia": {"slide"},
    "tenis": {"calcado", "calcados"},
    "camiseta": {"camisa", "camisetas"},
    "camera": {"cameras"},
    "calca": {"jeans"},
    "roupa": {"guarda"},
    "mochila": {"bolsa"},
    "bolsa": {"mochila"},
    "cesto": {"organizador"},
    "pantufa": {"chinelo"},
    "tapete": {"passadeira"},
    "colchao": {"cama"},
}


def _compose_title_head_phrase(title: str, category: str, head: str) -> str | None:
    matches = list(re.finditer(r"[A-Za-zÀ-ÿ0-9]+", str(title or "")))
    if not matches:
        return None
    head_index = next(
        (
            index for index, match in enumerate(matches)
            if _fold_word(match.group(0)) == _fold_word(category)
        ),
        None,
    )
    if head_index is None:
        return None

    # Restrict inference to the same title clause. Marketplace listings often
    # append alternatives after punctuation, where an attribute may belong to
    # a different product in the same listing.
    clause_end = len(str(title))
    for marker in (",", ";", "|", "/", "—", "–", " - "):
        position = str(title).find(marker, matches[head_index].end())
        while (
            marker == ","
            and position > 0
            and position + 1 < len(str(title))
            and str(title)[position - 1].isdigit()
            and str(title)[position + 1].isdigit()
        ):
            position = str(title).find(marker, position + 1)
        if position >= 0:
            clause_end = min(clause_end, position)

    title_tokens = [match.group(0) for match in matches]
    folded_tokens = [_fold_word(token) for token in title_tokens]
    noun_heads = {_fold_word(value) for value in _KNOWN_PRODUCT_HEAD_TERMS}
    stop_words = {
        "a", "as", "o", "os", "um", "uma", "uns", "umas", "e",
        "na", "nas", "no", "nos", "ate", "por", "pra", "pro",
    }
    identity_words_skipped = 0
    for index in range(head_index + 1, min(len(matches), head_index + 13)):
        match = matches[index]
        if match.start() >= clause_end:
            break
        token = title_tokens[index]
        folded = folded_tokens[index]

        # Measurements and model identifiers can sit between the product
        # noun and a clear feature (for example, a curtain title followed by
        # "300 LEDs"). Skip them while preserving the title clause boundary.
        if any(char.isdigit() for char in token):
            continue
        if folded in _TITLE_PHRASE_NOISE or folded in stop_words:
            continue
        if folded in _TITLE_PHRASE_SKIP_BEFORE_DETAIL:
            continue

        relation_detail = _TITLE_PHRASE_DETAIL_RELATIONS.get(folded)
        if relation_detail:
            return f"{head} {relation_detail}"

        feature = None
        for size in (3, 2):
            phrase = tuple(folded_tokens[index:index + size])
            candidate = _TITLE_PHRASE_FEATURES.get(phrase)
            if candidate and index + size <= len(matches):
                feature = candidate
                break
        if feature:
            return f"{head} {feature}"

        if folded in _TITLE_SYNONYM_HEADS.get(_fold_word(category), set()):
            continue

        if folded in noun_heads:
            pair = (_fold_word(category), folded)
            conjunction = _TITLE_COMPOUND_PRODUCT_PAIRS.get(pair)
            if conjunction and index == head_index + 1:
                return f"{head} {conjunction} {token.casefold()}"
            # A second product class usually marks a bundle or an ambiguous
            # marketplace listing, so do not attach a later adjective to it.
            break

        adjective = _TITLE_PHRASE_ADJECTIVES.get(folded)
        if adjective:
            adjective = _agree_detail_with_head(head, adjective)
            return f"{head} {adjective}"

        if folded in _TITLE_RELATION_WORDS:
            complement: list[str] = []
            for object_index in range(index + 1, min(len(matches), index + 4)):
                object_match = matches[object_index]
                if object_match.start() >= clause_end:
                    break
                object_folded = folded_tokens[object_index]
                object_token = title_tokens[object_index]
                if any(char.isdigit() for char in object_token):
                    break
                if object_folded in _TITLE_RELATION_WORDS or object_folded in stop_words:
                    break
                if (
                    object_folded in noun_heads
                    and object_folded not in _TITLE_RELATION_PRODUCT_OBJECTS
                ):
                    break
                if object_folded in _TITLE_PHRASE_NOISE:
                    break
                if not complement or object_folded in _TITLE_PHRASE_ADJECTIVES:
                    complement.append(object_token.casefold())
                else:
                    break
            if complement:
                relation = token.casefold()
                object_text = _fold_word(" ".join(complement))
                if relation == "de" and _fold_word(category) in {
                    "copo", "copos", "caneca", "canecas", "xicara", "xicaras", "garrafa", "garrafas",
                } and object_text == "cafe":
                    relation = "para"
                object_phrase = " ".join(
                    "Natal" if _fold_word(value) == "natal" else value
                    for value in complement
                )
                caption = f"{head} {relation} {object_phrase}"
                if len(caption.split()) <= 5:
                    return caption
            continue

        # Seller titles often place a brand or a model between the product and
        # its feature. Skip a small number of unknown tokens, but stop at a
        # second product class or title-clause boundary. Only a detail from the
        # explicit vocabulary above can become caption text.
        identity_words_skipped += 1
        if identity_words_skipped <= 6:
            continue
        break
    return None


def _compose_category_head_fact(
    raw_fact: str, category: str, normalize_fact: Any,
) -> str | None:
    words = re.findall(r"[A-Za-zÀ-ÿ]+(?:[-'][A-Za-zÀ-ÿ]+)*", str(raw_fact or ""))
    if not 2 <= len(words) <= 5:
        return None
    if any(any(char.isdigit() for char in word) for word in words):
        return None
    first = _fold_word(words[0])
    target = _fold_word(category)
    if first != target and first.removesuffix("s") != target.removesuffix("s"):
        return None
    phrase = str(normalize_fact(raw_fact) or "").strip()
    if not phrase:
        return None
    return phrase[0].upper() + phrase[1:]


def title_fact_is_attached_to_product(title: str, category: str, fact: str) -> bool:
    """Avoid pairing a fact from a later, unrelated clause with the product."""
    folded_title = _fold(title)
    category_match = re.search(rf"\b{re.escape(_fold_word(category))}\b", folded_title)
    if category_match is None:
        return False

    fact_key = _fold(fact)
    exact_fact = re.search(rf"\b{re.escape(fact_key)}\b", folded_title)
    if exact_fact is None:
        # A fact absent from the seller title may come from a Vision description
        # or a structured attribute, which is already tied to this product.
        return True
    if exact_fact.start() < category_match.start():
        return False

    between = folded_title[category_match.end():exact_fact.start()]
    # Decimal specifications are still part of the same title clause; their
    # point should not detach a later, nonnumeric feature such as AMOLED.
    between = re.sub(r"(?<=\d)\.(?=\d)", "", between)
    if any(mark in between for mark in (",", ";", "|", ".")):
        return False
    # A feature noun between the product class and a material/attribute can
    # own that detail. For example, in "calça ... cinto de couro", leather
    # describes the belt, not the trousers.
    if re.search(r"\b(?:cinto|cintos|al[cç]a|al[cç]as|bolso|bolsos|cabo|cabos)\b", between):
        return False
    return len(between) <= 80 and len(between.split()) <= 12


def _display_title_head(title: str, category: str) -> str | None:
    canonical = {
        "baba": "Babá", "camera": "Câmera", "calca": "Calça",
        "cafe": "Café", "lencol": "Lençol", "mascara": "Máscara",
        "oculos": "Óculos", "oleo": "Óleo", "luminaria": "Luminária",
        "pa": "Pá", "po": "Pó",
        "relogio": "Relógio", "sandalia": "Sandália", "tenis": "Tênis",
        "xicara": "Xícara", "xicaras": "Xícaras", "arvore": "Árvore",
    }
    for raw in re.findall(r"[A-Za-zÀ-ÿ]+(?:[-'][A-Za-zÀ-ÿ]+)*", title):
        if _fold_word(raw) == _fold_word(category):
            if _fold_word(category) in canonical:
                return canonical[_fold_word(category)]
            if _fold_word(category) in {"tv", "ssd", "pc", "led"}:
                return raw.upper()
            return raw[0].upper() + raw[1:].lower()
    return None


def _agree_detail_with_head(head: str, detail: str) -> str:
    if not _fold_word(head).endswith("s"):
        return detail
    plural = {
        "leve": "leves",
        "dobrável": "dobráveis",
        "retrátil": "retráteis",
        "ajustável": "ajustáveis",
        "recarregável": "recarregáveis",
        "transparente": "transparentes",
        "inoxidável": "inoxidáveis",
        "regulável": "reguláveis",
        "giratório": "giratórios",
        "giratória": "giratórias",
        "peludo": "peludos",
        "peluda": "peludas",
        "antiaderente": "antiaderentes",
        "antiderrapante": "antiderrapantes",
    }
    return plural.get(detail, detail)


def _render_title_detail(raw_fact: str, category: str) -> str | None:
    fact = re.sub(r"\s+", " ", str(raw_fact or "")).strip()
    folded = _fold(fact)
    lower = fact[:1].lower() + fact[1:]

    exact = {
        "algodao": "de algodão",
        "aluminio": "de alumínio",
        "aco": "de aço",
        "aco inoxidavel": "de aço inoxidável",
        "microfibra": "de microfibra",
        "madeira": "de madeira",
        "vidro": "de vidro",
        "silicone": "de silicone",
        "plastico": "de plástico",
        "nylon": "de nylon",
        "poliester": "de poliéster",
        "couro": "de couro",
        "camurca": "em camurça",
        "suede": "em suede",
        "trico": "de tricô",
        "inox": "em inox",
        "strass": "com strass",
        "detalhes em strass": "com strass",
        "display digital": "com display digital",
        "mostrador digital": "com mostrador digital",
        "corte a laser": "com corte a laser",
        "ilha dinamica": "com ilha dinâmica",
        "cintura alta": "de cintura alta",
        "bojo": "com bojo",
        "forro": "com forro",
        "dupla camada": "de dupla camada",
        "estampa floral": "com estampa floral",
        "detalhe floral": "com detalhe floral",
        "estampa de poa": "com estampa de poá",
        "estampa xadrez": "com estampa xadrez",
        "formato quadrado": "em formato quadrado",
        "cores variadas": "em cores variadas",
        "cabo de aco": "com cabo de aço",
        "compartimento de almoco": "com espaço para almoço",
        "leve e confortavel": "leve e confortável",
        "textura canelada": "com textura canelada",
        "leve": "leve",
        "dobravel": "dobrável",
        "retratil": "retrátil",
        "ajustavel": "ajustável",
        "recarregavel": "recarregável",
        "transparente": "transparente",
        "inoxidavel": "de aço inoxidável",
        "controle remoto": "com controle remoto",
        "conexao bluetooth": "com Bluetooth",
        "acabamento dourado": "com acabamento dourado",
        "acabamento matte": "com acabamento matte",
        "toque macio": "com toque macio",
        "uso no treino": "para o treino",
        "tom ambar": "em tom âmbar",
        "material sintetico": "de material sintético",
        "material escolar": "para a escola",
        "cabo usb": "com cabo USB",
        "bolsos laterais": "com bolsos laterais",
        "manga bufante": "de manga bufante",
        "suplex": "de suplex",
        "hidratação corporal": "para hidratação corporal",
        "hidratacao corporal": "para hidratação corporal",
        "hidratacao facial": "para hidratação facial",
        "estilo classico": "de estilo clássico",
        "solado plataforma": "com plataforma no solado",
        "a prova d'agua": "à prova d’água",
        "a prova dagua": "à prova d’água",
        "antiaderente": "antiaderente",
        "com brilho": "com brilho",
        "tela super amoled": "com tela Super AMOLED",
        "tela amoled": "com tela AMOLED",
        "super amoled": "com tela Super AMOLED",
        "amoled": "com tela AMOLED",
    }
    if folded in exact:
        return exact[folded]

    for prefix in ("bico ", "manga ", "cano ", "salto "):
        if folded.startswith(prefix):
            return f"de {lower}"
    for prefix in ("gola ", "alca ", "alcas ", "tira ", "tiras ", "fivela ", "fivelas "):
        if folded.startswith(prefix):
            return f"com {lower}"
    if folded.startswith("estampa "):
        if folded.startswith("estampa de "):
            lower = "estampa " + lower[len("estampa de "):]
        return f"com {lower}"
    if folded.startswith("pingente "):
        if re.search(r"\b(?:cora[cç][aã]o|flor|letras?|inicial|foto)\b", folded):
            return f"com {lower}"
        return None
    if folded.startswith("display ") or folded.startswith("visor "):
        return f"com {lower}"
    if folded.startswith("formato "):
        return f"em {lower}"
    if folded.startswith("compartimento "):
        return f"com {lower}"

    # A one-word detail such as "digital" is meaningful only with the
    # product classes that use it as a standard caption descriptor.
    if folded == "digital" and category in {"relogio", "smartwatch", "copo"}:
        return "digital"
    if folded == "cafe" and category in {
        "xicara", "xicaras", "caneca", "copo", "garrafa", "cafeteira",
    }:
        return "para café"
    return None


def compose_neutral_caption_fallback(
    context: dict[str, Any],
) -> TitleRuleCaption | None:
    """Create a no-claim caption when Vision identified a product but no safe
    product detail could be composed from its persisted context.

    This is deliberately a last resort in CaptionGenerator. It must never
    outrank a caption grounded in an explicit product fact.
    """
    title = str(context.get("productName") or "").strip()
    if not title:
        return None

    folded_title = _fold(title)
    if re.search(r"\b(?:frasco|frascos|dispenser|dispensador)\b", folded_title) and re.search(
        r"\b(?:shampoo|condicionador)\b", folded_title,
    ):
        if re.search(r"\bviagem\b", folded_title):
            return TitleRuleCaption(
                caption="Acessórios para viagem",
                category="viagem",
                hashtag="viagem",
                evidence=("acessórios de viagem",),
            )
        if re.search(r"\bbanheiro\b", folded_title):
            return TitleRuleCaption(
                caption="Itens para o banheiro",
                category="banheiro",
                hashtag="banheiro",
                evidence=("kit banheiro",),
            )

    anchors = tuple(
        _fold_word(term)
        for term in caption_product_anchor_terms(context, product_name=title)
        if _fold_word(term)
    )
    category_sequence = tuple(
        _fold_word(term)
        for term in caption_product_category_terms(title, context)
        if _fold_word(term)
    )
    category_terms = set(category_sequence)
    if re.search(r"\bsaida\s+de\s+praia\b", _fold(title)):
        category_terms.add("saida")
        hashtag_override = "saidadepraia"
    else:
        hashtag_override = None
    hashtag = hashtag_override or next(
        (
            term for term in anchors
            if term in category_terms and len(term) <= 20
        ),
        None,
    )
    if not hashtag:
        hashtag = next(
            (term for term in category_sequence if len(term) <= 20),
            None,
        )
    if not hashtag:
        hashtag = next(
            (term for term in anchors if len(term) <= 20),
            None,
        )

    if (
        category_terms & {"xicara", "caneca", "copo"}
        and re.search(r"\bcaf[eé]\b", folded_title)
    ):
        return TitleRuleCaption(
            caption="Café quentinho",
            category=next(iter(category_terms & {"xicara", "caneca", "copo"})),
            hashtag="cafe",
            evidence=("café",),
        )
    # The final safety net names the recognized product class instead of
    # generating a broad lifestyle sentence. It adds no product property or
    # benefit, and never falls back to a generic hashtag such as #achados.
    if not hashtag or not category_sequence:
        return None
    category = next((term for term in category_sequence if term not in _GENERIC_HASHTAGS), None)
    if not category:
        return None
    head = _display_title_head(title, category)
    if not head:
        head = category.replace("_", " ").strip().capitalize()
    if not head:
        return None

    # When the title contains no trustworthy detail, use only the recognized
    # product head. A short factual noun phrase is preferable to empty filler.
    caption = head
    return TitleRuleCaption(
        caption=caption,
        category=category,
        hashtag=hashtag,
        evidence=("fallback neutro sem alegação sobre características do produto",),
    )


def compose_title_rule_evidence(
    context: dict[str, Any], candidates: tuple[str, ...] | list[str],
) -> dict[str, dict[str, Any]]:
    rule = compose_title_rule_caption(context)
    if rule is None:
        return {}
    full_caption = rule.full_caption
    if full_caption not in candidates:
        return {}
    return {
        full_caption: {
            "caption": rule.caption,
            "category": rule.category,
            "hashtag": rule.hashtag,
            "facts": list(rule.evidence),
        }
    }
