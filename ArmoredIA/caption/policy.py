from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

FORBIDDEN_WORDS = {"embalagem", "tampa", "frasco", "lacre"}
SALES_WORDS = {
    "compre", "comprar", "garanta", "garantir", "imperdivel", "imperdível",
    "aproveite", "oferta", "ofertas", "promocao", "promoção", "desconto",
    "corra", "nao perca", "não perca",
}
SALES_PHRASES = {"leve essa", "leve esse", "leva essa", "leva esse"}
# Broad Unicode emoji ranges plus legacy emoji-presentation symbols.
# Also remove selectors, joiners, modifiers and keycap/tag components.
EMOJI_RE = re.compile(
    "[\\U0001F1E6-\\U0001F1FF\\U0001F300-\\U0001FAFF"
    "\\U00002300-\\U000023FF\\U00002600-\\U000027BF"
    "\\U00002B00-\\U00002BFF\\U0001FC00-\\U0001FFFF"
    "\\u00A9\\u00AE\\u203C\\u2049\\u2122\\u2139\\u3030\\u303D\\u3297\\u3299]"
)
EMOJI_COMPONENT_RE = re.compile(
    "[\\uFE0E\\uFE0F\\u200D\\u20E3\\U0001F3FB-\\U0001F3FF"
    "\\U000E0020-\\U000E007F]"
)
def _remove_emojis(text: str) -> str:
    value = str(text or "")
    for key in "#*0123456789":
        value = value.replace(key + "\ufe0f\u20e3", "")
        value = value.replace(key + "\u20e3", "")
    value = EMOJI_RE.sub("", value)
    return EMOJI_COMPONENT_RE.sub("", value)
HASHTAG_RE = re.compile(r"(?<!\w)#([\wÀ-ÿ]+)", re.UNICODE)
WORD_RE = re.compile(r"[A-Za-zÀ-ÿ0-9]+(?:['-][A-Za-zÀ-ÿ0-9]+)?", re.UNICODE)
PRODUCT_STOP_WORDS = {
    "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos", "e",
    "em", "na", "nas", "no", "nos", "para", "por", "pro", "pra", "sem",
    "um", "uma", "o", "os",
    "kit", "conjunto", "novo", "nova", "olha", "olhe",
    "esse", "essa", "isso", "ate",
    # Generic marketplace placeholders do not identify a product category.
    "produto", "produtos", "tipo",
}

_CONTEXT_FIELDS = (
    "productName", "category", "categoryName", "productCategory", "productType",
    "description", "usage", "useCase", "style", "appearance", "attributes",
)
_CATEGORY_FIELDS = ("category", "categoryName", "productCategory", "productType")
_HASHTAG_CONTEXT_ALIASES = {
    "casa": {"casa", "cozinha", "bancada", "mesa", "sala", "quarto", "banheiro", "organizador", "utensilio", "decoracao"},
    "cozinha": {"cozinha", "bancada", "utensilio", "preparo", "culinaria", "cozinhar", "descascador", "legumes", "vegetais"},
    "decor": {"decor", "decoracao", "sala", "quarto", "ambiente", "casa"},
    "decoracao": {"decor", "decoracao", "sala", "quarto", "ambiente", "casa"},
    "papelaria": {"papelaria", "marcatexto", "marcador", "caneta", "caderno", "escrita"},
    "organizacao": {"organizacao", "organizador", "gaveta", "prateleira", "armazenamento", "casa", "cozinha"},
    "moda": {"moda", "tenis", "calcado", "calcados", "sapato", "sandalia", "vestuario", "roupa", "feminino", "masculino", "casual", "camurca"},
    "beleza": {"beleza", "batom", "esmalte", "maquiagem", "cosmetico", "unha", "skincare"},
    "iluminacao": {"iluminacao", "luz", "abajur", "luminaria", "lampada"},
    "chinelo": {"calcado", "calcados", "sapato", "sandalia", "tenis", "bota", "sapatilha"},
    "sandalia": {"calcado", "calcados", "sapato", "chinelo", "tenis", "bota", "sapatilha"},
    "tenis": {"calcado", "calcados", "sapato", "sandalia", "chinelo", "bota", "sapatilha"},
    "tanga": {"calcinha", "calcinhas", "lingerie"},
    "calcinha": {"tanga", "lingerie"},
    "calcinhas": {"tanga", "lingerie"},
    "calcado": {"calcado", "calcados", "sapato", "sandalia", "chinelo", "tenis", "bota", "sapatilha"},
}
_GENERIC_HASHTAGS = {
    "achados", "comprinhas", "viral", "fyp", "trending", "top", "legal",
    "show", "insta", "instagram", "produto", "produtos", "oficial",
}
_NEUTRAL_REACTION_WORDS = {
    "parece", "parecem", "olha", "olhe", "detalhe", "destaque",
    "ate", "esse", "essa", "isso", "um", "uma", "o", "a", "pro", "pra",
    # These words frame a short editorial comment. A grounded product detail
    # still has to appear in the sentence, and the hard claim/sales filters
    # below continue to reject invented benefits and promotional language.
    "e", "sao", "tem", "têm", "esta", "estao", "fica", "ficam", "vem", "vêm",
    "pode", "podem", "ser", "que", "aparece", "aparecem", "lembra", "como", "tipo",
    "toque", "clima", "composicao", "tecido", "textura", "acabamento",
    "modelagem", "estampa", "padronagem", "mostrador", "formato",
    "compoe", "interior", "interno", "acompanha", "acompanham", "detalhes",
    "tom", "pecas", "contém", "contem", "evidencia", "estrutura",
    "presente", "se", "sob", "traz", "serve", "apresenta", "foco",
    # These are the owner's approved editorial expressions, not product claims.
    "voce", "merece", "quentinho", "quentinha", "quentinhos", "quentinhas",
    "cantinho", "cantinhos",
}
_VISION_UNTRUSTED_CLAIM_WORDS = {
    # Marketplace copy and broad promises are not reliable product facts.
    "avancado", "avancada", "avancados", "avancadas", "blogueira",
    "blogueiras", "crescimento", "elegante", "elegancia", "garantia",
    "garantido", "garantida", "incrivel", "incriveis", "lindo", "linda",
    "lindos", "lindas", "luxo", "perfeito", "perfeita", "premium", "protecao", "protegido",
    "impecavel", "impecaveis",
    "protegida", "sofisticado", "sofisticada", "superior", "tecnologia",
    "tendencia", "tendencias", "viral", "milagre", "milagroso", "milagrosa",
    "original", "modelo", "modelos",
    "promete", "prometem", "resultado", "resultados",
}
_GENERATION_REACTION_WORDS = {
    "parece", "olha", "olhe",
}
_COMPARISON_MARKERS = {"parece", "tipo", "como", "lembra"}
_COMPARATIVE_TITLE_NOUNS = {"apontador", "apontadores"}
# Product nouns and the short reaction adjectives exposed to Ollama. The
# caption has only two or three words, so a small morphology check catches
# high-impact agreement errors without pretending to be a full Portuguese
# grammar engine.
_GENDERED_PRODUCT_NOUNS = {
    "escova": ("f", "s"), "escovas": ("f", "p"),
    "descascador": ("m", "s"), "descascadores": ("m", "p"),
    "apontador": ("m", "s"), "apontadores": ("m", "p"),
    "bolsa": ("f", "s"), "bolsas": ("f", "p"),
    "caneca": ("f", "s"), "canecas": ("f", "p"),
    "mesa": ("f", "s"), "mesas": ("f", "p"),
    "cadeira": ("f", "s"), "cadeiras": ("f", "p"),
    "blusa": ("f", "s"), "blusas": ("f", "p"),
    "camisa": ("f", "s"), "camisas": ("f", "p"),
    "sandalia": ("f", "s"), "sandalias": ("f", "p"),
    "panela": ("f", "s"), "panelas": ("f", "p"),
    "mochila": ("f", "s"), "mochilas": ("f", "p"),
    "mascara": ("f", "s"), "mascaras": ("f", "p"),
    "luminaria": ("f", "s"), "luminarias": ("f", "p"),
    "bebida": ("f", "s"), "bebidas": ("f", "p"),
    "chinelo": ("m", "s"), "chinelos": ("m", "p"),
    "cafe": ("m", "s"), "cafes": ("m", "p"),
    # "tênis" has the same written form in singular and plural.
    "tenis": ("m", None), "sapato": ("m", "s"), "sapatos": ("m", "p"),
    "scarpin": ("m", "s"), "scarpins": ("m", "p"),
    "smartwatch": ("m", "s"), "relogio": ("m", "s"),
    "radio": ("m", "s"), "radios": ("m", "p"),
    "sofa": ("m", "s"), "sofas": ("m", "p"),
    "organizador": ("m", "s"), "organizadores": ("m", "p"),
    "abajur": ("m", "s"), "abajures": ("m", "p"),
    "celular": ("m", "s"), "celulares": ("m", "p"),
    "fone": ("m", "s"), "fones": ("m", "p"),
    "coracao": ("m", "s"), "coracoes": ("m", "p"),
    "tamanco": ("m", "s"), "tamancos": ("m", "p"),
    "tira": ("f", "s"), "tiras": ("f", "p"),
    "bico": ("m", "s"), "bicos": ("m", "p"),
    "colete": ("m", "s"), "coletes": ("m", "p"),
    "cachecol": ("m", "s"), "cachecois": ("m", "p"),
    "lenco": ("m", "s"), "lencos": ("m", "p"),
    "echarpe": ("f", "s"), "echarpes": ("f", "p"),
    "pashmina": ("f", "s"), "pashminas": ("f", "p"),
    "caneta": ("f", "s"), "canetas": ("f", "p"),
    "body": ("m", "s"), "protetor": ("m", "s"), "protetores": ("m", "p"),
    "pulseira": ("f", "s"), "pulseiras": ("f", "p"),
    "calca": ("f", "s"), "calcas": ("f", "p"),
    "oculos": ("m", "p"), "xicara": ("f", "s"), "xicaras": ("f", "p"),
    "radio": ("m", "s"), "radios": ("m", "p"),
    "bracelete": ("m", "s"), "braceletes": ("m", "p"),
    "blusinha": ("f", "s"), "blusinhas": ("f", "p"),
    "calcinha": ("f", "s"), "calcinhas": ("f", "p"),
    "sutia": ("m", "s"), "sutias": ("m", "p"),
    "vestido": ("m", "s"), "vestidos": ("m", "p"),
    "moletom": ("m", "s"), "moletons": ("m", "p"),
    "casaco": ("m", "s"), "casacos": ("m", "p"),
    "touca": ("f", "s"), "toucas": ("f", "p"),
    "oleo": ("m", "s"), "oleos": ("m", "p"),
    "parca": ("f", "s"), "parcas": ("f", "p"),
    "bota": ("f", "s"), "botas": ("f", "p"),
    "pantufa": ("f", "s"), "pantufas": ("f", "p"),
}
_KNOWN_PRODUCT_HEAD_TERMS = (
    (
        set(_GENDERED_PRODUCT_NOUNS)
        | {
        "calcado", "calcados", "chinelo", "sandalia", "sapato", "tenis",
        "bota", "sapatilha", "roupa", "vestuario", "luz", "abajur",
        "smartwatch", "relogio",
        "scarpin", "scarpins",
        "marcatexto", "marcador", "delineador", "arandela", "arandelas",
        "escrivaninha", "ferramenta", "ferramentas", "fantasia", "aparador",
        "mouse", "prancha", "tabua", "gabinete", "purificador", "boneco",
        "bonecos", "churrasqueira", "saco", "soprador", "extensao", "nicho",
        "chapeu", "frigobar", "boleira", "cenario", "cobreleito", "cercadinho",
        "dispensador", "aparelho", "paleta", "lixador", "serra", "passador",
        "esponja", "peruca", "caderneta", "babuche", "desodorante", "farinha",
        "suplemento", "creatina", "tinta", "airfryer", "volante", "impressora",
        "rotulador", "laminadora", "gimbal", "carrossel", "tiara", "serpentina",
        "confete", "bloquinho", "fato", "roupao", "album", "diario", "calculadora",
        "cartela", "palheta", "toalheiro", "massager", "utensil", "soquete",
        "soquetes", "biberon", "estabilizador", "recipiente", "refil", "bichinho",
        "luminaria", "lampada", "batom", "esmalte", "maquiagem",
        "cesta", "cestas", "lustre", "adaptador", "adaptadores",
        "cosmetico", "unha", "skincare", "utensilio", "panela",
        "frigideira", "talher", "mesa", "bancada", "escova", "escovas",
        "colar", "colares", "brinco", "brincos", "pulseira", "pulseiras",
        "anel", "aneis", "joia", "joias",
        "copo", "copos", "gel", "gels", "limpeza", "garrafa", "garrafas",
        "creme", "shampoo", "condicionador", "sabonete", "perfume", "base",
        "descascador", "descascadores", "calcinhas", "calcinha", "tanga",
        "macaquinho", "macaquinhos", "cortina", "cortinas", "capa", "capinha",
        "pote", "potes", "lencol", "lencois", "armario", "armarios", "maquina", "quadriciclo",
        "suporte", "suportes", "caixa", "caixas", "brinquedo", "brinquedos",
        "tapete", "tapetes", "espelho", "espelhos", "caderno", "cadernos",
        "cama", "camas", "camera", "cameras", "cortador", "cortadores",
        "fatiador", "fatiadores", "arvore", "arvores", "bicicleta", "bicicletas",
        "amplificador", "lupa", "flanela", "boneca", "bonecas", "fryer",
        "cerveja", "pacoca", "maio", "papai", "borracha", "apagador",
        "quebra", "bastao", "cozedor", "tostadeira", "alca", "alcas",
        "pet", "ejetor", "globo", "blush", "capas",
        "triciclo", "triciclos", "lousa", "lapis", "livro", "livros",
        "penteadeira", "penteadeiras", "prateleira", "prateleiras", "sapateira",
        "sapateiras", "chaleira", "chaleiras", "aquecedor", "aquecedores",
        "ventilador", "ventiladores", "microondas", "liquidificador",
        "liquidificadores", "bebedouro", "bebedouros", "comedouro", "comedouros",
        "joelheira", "joelheiras", "serum", "massageador", "massageadores",
        "rolo", "lixeira", "lixeiras", "bola", "bolas", "carrinho", "carrinhos",
        "chaveiro", "chaveiros", "compressor", "compressores", "filtro", "filtros",
        "banqueta", "banquetas", "caminha", "caminhas", "esmaltes", "fritadeira",
        "fritadeiras", "forma", "formas", "saladeira", "saladeiras", "sanduicheira",
        "rack", "racks", "furadeira", "furadeiras",
        "parafusadeira", "parafusadeiras", "troninho", "penico", "penicos",
        "coador", "coadores", "moedor", "moedores", "desfiador", "desfiadores",
        "portaretrato", "adesivo",
        "adesivos", "vaso", "vasos", "panificadora", "forno", "fornos",
        "cafeteira", "cafeteiras",
        "aplique", "estante", "cuba", "comoda", "balcao", "cooktop",
        "projetor", "projetores", "smartphone", "smartphones", "umidificador",
        "umidificadores", "toalha", "toalhas", "pacoca", "pa", "po", "tonico", "tonicos",
        "papel", "banheira", "lona", "travesseiro", "travesseiros",
        "sanduicheiras",
        "vara", "varas", "cola", "macacao", "macacoes", "edredom", "edredons",
        "coleira", "coleiras", "mangueira", "mangueiras", "estacao", "bastao", "bastoes",
        "grampeador", "grampeadores", "removedor", "removedores",
        "seladora", "seladoras", "cropped", "cofre", "cofres", "jaqueta", "jaquetas",
        "estojo", "estojos", "rimel", "andador", "andadores", "pisca",
        "placa", "placas", "ssd", "almofada", "almofadas", "pistola", "pistolas",
        "rechaud", "patins", "cubo", "cubos", "teclado", "biblioteca", "biblia",
        "pista", "arandela", "mop", "prendedor", "ralo", "ralos", "alicate",
        "luva", "luvas", "bandeira", "bandeiras", "retrato", "luminaria",
        "passadeira", "colcha", "petisqueira", "marmitex", "terco", "vela",
        "cesto", "pano", "panos", "talher", "talheres", "prato", "pratos",
        "jarra", "jarras", "fita", "fitas", "painel", "aspirador",
        "carregador", "ferro", "colchao", "mala", "malas", "secador",
        "balanca", "espremedor", "processador", "tigela", "tigelas", "gloss",
        "blush", "hidratante", "grade", "portao", "capacete", "controle",
        "trena", "modelador", "carteira", "taca", "tacas", "escorredor",
        "cadeirinha", "banheira", "presilha", "clipe", "gancho", "vassoura",
        "maleta", "marmita", "bomba", "dispenser", "ferramenta", "ferramentas",
        "extensor", "ventosa", "piscina", "guirlanda", "guarda-chuva",
        "esfoliante", "vestido", "poncho", "sutia", "moletom", "pijama",
        "pijamas", "saia", "saias", "short", "shorts", "shortinho", "shortinhos",
        "legging", "leggings", "jardineira", "jardineiras",
        "kimono", "saida", "ativador", "ativadores", "sache", "saches",
        "blusa", "blusas", "camiseta", "camisetas", "meia", "meias",
        "cinto", "cintos", "bandeja", "pincel", "pinceis",
        "pa", "po", "chuteira", "chuteiras", "enfeite", "enfeites",
        "televisor", "televisao", "tv", "mixer", "torradeira", "esponja",
        "ducha", "chuveiro", "berco", "fraldinha", "trocador", "cobertor",
        "manta", "mesinha", "baralho", "pelicula", "resina", "fechadura",
        "carimbo", "panquequeira", "omeleteira", "fichario", "tesoura",
        "regua", "vaporizador", "pipoqueira", "cooler", "puff", "cabideiro",
        "bone", "patinete", "esteira", "varal", "microfone", "batedeira",
        "tablet", "cueca", "cuecas", "camisola", "chave", "facas", "faca",
        "colonia", "desodorante", "marcador", "marcatexto", "inalador",
        "nebulizador", "geladeira", "mousse", "gamepad", "console", "arco",
        "galheteiro", "galheteiros", "papete", "rasteira", "rasteirinha",
        "gaveteiro", "fruteira", "otoscopio", "mobile", "cadarco", "cadarcos",
        "capinha", "amplificador", "cordao", "aparelho", "simulador", "curativo",
        "curativos", "clipe", "clipes", "broche", "pin", "spinner", "aplicador",
        "lavadora", "pulverizador", "irrigador", "cera", "poltrona", "balao",
        "baba", "calendario", "capacete", "jogo", "frase", "squeeze", "canecao",
        "berco", "faca", "fichario", "cinta", "fogao", "robo", "robot",
        "mosquiteiro", "robe", "sousplat", "monitor", "stepper", "rodo",
        "ondulador", "bata", "tunica", "sueter", "biberiao", "mamadeira",
        "balde", "barraca", "molde", "lavadora", "detergente", "sanduicheira",
        "alimento", "chocolate", "bombom", "desincoffee", "tubo", "iluminador",
        "barra", "limpador", "drone", "ventilador", "cacheador", "secador",
        "blush", "batom", "cinto", "chave", "manguito", "biberon", "squeeze",
        "cinta", "separador", "ninho", "cacto", "diorama", "afiador", "amolador",
        "mousse", "espuma", "spray", "rechaud", "liquidificador", "interruptor",
        }
    )
    - {"apontador", "apontadores"}
    | {
        # Additional reusable product heads found in the historical catalog.
        # These are product classes, not title-specific phrases or brands.
        "abridor", "abridores", "acessorio", "acessorios", "ampola", "ampolas",
        "balanco", "balancos", "bermuda", "bermudas", "espatula", "espatulas",
        "fecho", "fechos", "figura", "figuras", "fondue", "louca", "loucas",
        "pista", "pistas", "tint", "tints", "elefante", "elefantes", "lanterna",
        "lanternas", "linterna", "linternas", "porta-joias", "porta-ovos",
        "passadeira", "tapete", "tapetes", "cobreleito", "cobreleitos",
        "protetores", "protetor", "watchband", "watchbands", "pulseira",
        "pulseiras", "estojo", "estojos", "marmita", "marmitas", "camisola",
        "camisolas", "pasta", "pastas", "racao", "racoes", "rede", "redes",
        "persiana", "persianas", "talher", "talheres", "lenha", "sinalizador",
        "sinalizadores", "placa", "placas", "alimento", "alimentos", "violao",
        "cafeteira", "soda", "luz", "luzes", "estante", "estantes",
        "biquini", "biquinis", "quadro", "quadros", "poltrona", "poltronas",
        "estrela", "estrelas", "telao", "tempero", "temperos", "grip",
        "esfoliante", "esfoliantes", "gelatina", "notebook", "pinca", "pincas",
        "lanterna", "elefante", "cobreleito", "cobreleitos", "bolsinha", "bolsinhas",
        "fechadura", "abajur", "abajures", "caminhao", "caminhoes", "pelucia",
        "pelucias", "bala", "balas", "giz", "giz", "regata", "regatas",
        "tshirt", "viola", "trave", "traves", "bruma", "loção", "locao",
        "artesanato", "assadeira", "assadeiras", "assento", "assentos",
        "aspirador", "aspiradores", "balm", "balms", "bandejao", "betoneira",
        "betoneiras", "biberiao", "biberioes", "binoculo", "binoculos", "boia",
        "boias", "bowl", "bowls", "cabide", "cabides", "cacarola", "cacarolas",
        "campainha", "campainhas", "canudo", "canudos", "cascata", "cascatas",
        "centrifuga", "centrifugas", "chupeta", "chupetas", "cobreleito",
        "cobreleitos", "cueiro", "cueiros", "descamador", "descamadores",
        "difusor", "difusores", "edredom", "edredons", "elastico",
        "enfeite", "enfeites", "espremedor", "espremedores",
        "espartilho", "espartilhos", "estencil", "estencils", "extensor",
        "extensores", "faqueiro", "faqueiros", "figurinhas", "flutuador",
        "flutuadores", "fronha", "fronhas", "gamela", "gamelas", "grill",
        "grills", "hoverboard", "inclinometro", "inclinometros", "lanchonete",
        "lixa", "lixas", "lupa", "lupas", "maletinha", "maletinhas", "mamadeira",
        "mamadeiras", "massageador", "massageadores",
        "molheira", "molheiras", "mordedor", "mordedores", "necessaire", "necessaires",
        "odorizante", "odorizantes", "organizador", "organizadores", "pano", "panos",
        "passadeira", "passadeiras", "pasta", "pastas", "peneira", "peneiras",
        "pente", "pentes", "percarbonato", "pillow", "pin", "pins", "pintinho",
        "pintinhos", "politriz", "politrizes", "projetor", "projetores",
        "queijeira", "queijeiras", "refresqueira", "refresqueiras", "ripado",
        "ripados", "rodizio", "rodizios", "rodinha", "rodinhas", "saco", "sacos",
        "sapatilha", "sapatilhas", "saboneteira", "saboneteiras", "saia", "saias",
        "sunga", "sungas", "taça", "taca", "tacas", "talher", "talheres", "tapioqueira",
        "tapioqueiras", "toalha", "toalhas", "torneira", "torneiras", "travesseiro",
        "travesseiros", "utensilio", "utensilios", "vaselina", "vela", "velas",
        "ventosa", "ventosas", "watch", "whitener", "xicara", "xicaras",
    }
)
_REACTION_ADJECTIVE_PARADIGMS = {
    "bonit": {("m", "s"): "bonito", ("m", "p"): "bonitos", ("f", "s"): "bonita", ("f", "p"): "bonitas"},
    "lind": {("m", "s"): "lindo", ("m", "p"): "lindos", ("f", "s"): "linda", ("f", "p"): "lindas"},
    "charmos": {("m", "s"): "charmoso", ("m", "p"): "charmosos", ("f", "s"): "charmosa", ("f", "p"): "charmosas"},
    # Temperature terms are common in product captions and must agree in
    # number even though "quente" itself does not change for gender.
    "quent": {("m", "s"): "quente", ("m", "p"): "quentes", ("f", "s"): "quente", ("f", "p"): "quentes"},
    "fri": {("m", "s"): "frio", ("m", "p"): "frios", ("f", "s"): "fria", ("f", "p"): "frias"},
    "larg": {("m", "s"): "largo", ("m", "p"): "largos", ("f", "s"): "larga", ("f", "p"): "largas"},
}
_GENDERED_REACTION_ADJECTIVES = {
    form: agreement
    for paradigm in _REACTION_ADJECTIVE_PARADIGMS.values()
    for agreement, form in paradigm.items()
}
_GENDERED_REACTION_ADJECTIVES.update({"quente": ("x", "s"), "quentes": ("x", "p")})
_REACTION_ADJECTIVE_BASE = {
    form: base
    for base, paradigm in _REACTION_ADJECTIVE_PARADIGMS.items()
    for form in paradigm.values()
}
_MAIN_CONTEXT_ALIASES = {
    "trico": {"tricot"},
    "tricot": {"trico"},
    "descascar": {"descascador", "descascadores", "legumes", "vegetais"},
    "vegetais": {"legumes", "descascador", "descascadores"},
    "infantil": {"infantil", "menina", "menino", "crianca", "roupa"},
    "chinelo": {"calcado", "calcados", "uso", "casual"},
    "sandalia": {"calcado", "calcados", "uso", "casual"},
    "tenis": {"calcado", "calcados", "moda", "casual"},
    "calcado": {"calcado", "calcados", "moda", "casual"},
    "organizada": {"organizador", "organizacao"},
    "organizado": {"organizador", "organizacao"},
    "organizadas": {"organizador", "organizacao"},
    "organizados": {"organizador", "organizacao"},
    "moda": {"feminino", "masculino", "casual", "tenis", "calcado", "sapato", "sandalia", "roupa", "vestuario"},
    "casa": {"cozinha", "bancada", "mesa", "sala", "quarto", "banheiro", "organizador", "utensilio"},
    "cozinha": {"bancada", "utensilio", "preparo", "culinaria", "cozinhar", "descascador", "legumes", "vegetais"},
    "beleza": {"batom", "esmalte", "maquiagem", "cosmetico", "unha", "skincare"},
    "decoracao": {"decor", "sala", "quarto", "ambiente", "casa"},
    "organizacao": {"organizador", "gaveta", "prateleira", "armazenamento", "casa", "cozinha", "mesa"},
    "iluminacao": {"luz", "abajur", "luminaria", "lampada"},
    # Semantic paraphrases for the explicit Vision fact "caneta apagável".
    "escrita": {"caneta", "apagavel"},
    "escrever": {"caneta", "apagavel"},
    "apagada": {"caneta", "apagavel"},
    "apagado": {"caneta", "apagavel"},
    "apagar": {"caneta", "apagavel"},
    "apaga": {"caneta", "apagavel"},
    "permite": {"apagavel"},
    "correcao": {"caneta", "apagavel"},
    "correcoes": {"caneta", "apagavel"},
    # Direct semantic paraphrases of product-title facts. These do not add
    # visual claims: erasable gel-pen context supports its writing/trace;
    # "mula manca" is the persisted apparel descriptor for a one-shoulder cut;
    # anti-frizz and ribbed wording support their ordinary inflections.
    "traco": {"caneta", "gel", "apagavel"},
    "tracos": {"caneta", "gel", "apagavel"},
    "ombro": {"mula", "manca"},
    "assimetrico": {"mula", "manca"},
    "unico": {"mula", "manca"},
    "reduzir": {"antifrizz", "frizz"},
    "reduz": {"antifrizz", "frizz"},
    "puro": {"algodao", "100"},
    "canelado": {"canelada"},
    "toque": {"macio", "macia", "suave"},
    "foco": {"crescimento", "capilar", "hair"},
    "cuidado": {"olheiras", "tratamento", "olhos", "antirrugas"},
    "treino": {"casual", "esportes", "dia"},
    "mangas": {"variadas", "variados", "manga"},
    "variadas": {"variado", "variados", "manga", "mangas"},
    "variacao": {"variado", "variados", "manga", "mangas"},
    "tinta": {"caneta", "gel", "apagavel"},
    "tintas": {"caneta", "gel", "apagavel"},
    "monitor": {"mostrador", "relogio", "digital"},
    "mostradores": {"relogio", "digital"},
    "estampa": {"estampado", "estampada", "floral", "onca", "listrada"},
    "floral": {"flor", "flores", "presilha"},
    "padronagem": {"estampado", "floral", "onca", "listrada"},
    "armação": {"oculos", "quadrado"},
    "armacao": {"oculos", "quadrado"},
    "reducao": {"frizz"},
    "controle": {"frizz", "antifrizz"},
    "termico": {"protetor", "cabelo", "isolado", "almoco"},
    "tiras": {"cruzadas", "tira"},
    "cruzadas": {"tiras", "cruzada"},
    "recorte": {"mula", "manca"},
    "design": {"mula", "manca"},
    "formato": {"quadrado", "nuvem", "coracao", "dedo"},
    "marcada": {"acinturado", "compressao"},
    "cintura": {"acinturado", "compressao"},
    "fios": {"cabelo", "hair", "mascara", "acidificante"},
    "pele": {"esfoliante", "corporal", "hidratante"},
    "isolado": {"almoco", "compartimento"},
    "isolada": {"almoco", "compartimento"},
    "refeicoes": {"almoco"},
    "aplicacao": {"strass"},
    "aplicacoes": {"strass"},
    "conexao": {"wifi", "bluetooth"},
    "wireless": {"wifi", "bluetooth"},
    "multimidia": {"radio", "carro", "autoradio"},
    "internos": {"forro", "bojo"},
    "frio": {"inverno"},
    "frios": {"inverno"},
    "dias": {"inverno"},
    "mostrador": {"digital", "relogio", "quadrado"},
    "solado": {"plataforma"},
    "base": {"plataforma"},
    "capilar": {"hair", "cabelo", "crescimento"},
    "manter": {"termico", "quente", "frio"},
    "equilibra": {"equilibrio"},
    "olhos": {"olheiras", "mascara"},
    "controlar": {"frizz", "antifrizz"},
    "protecao": {"protetor", "termico"},
    "inteiramente": {"100", "algodao"},
    "produzido": {"100", "algodao", "poliester"},
    "tom": {"ambar", "dourada", "douradas"},
    "tonalidade": {"rosa", "dourada", "dourado"},
    "toque": {"dourada", "douradas", "suede", "macio", "macia", "suave"},
    "pecas": {"xicaras", "canecas"},
    "mais": {"microfibra", "reforcado"},
    "estruturado": {"reforcado", "bojo"},
    "crescimento": {"hair", "capilar"},
    "felina": {"onca"},
    "mescla": {"algodao", "poliester", "50"},
    "composicao": {"algodao", "poliester", "100", "50"},
    "hidratacao": {"hidratante", "labial", "colageno"},
    "discreto": {"invisivel", "laser", "roupa"},
    "discreta": {"invisivel", "laser", "roupa"},
    "discricao": {"invisivel", "laser", "roupa"},
    "capilar": {"hair", "cabelo", "crescimento"},
    "visualmente": {"quadrado", "digital"},
    "ilha": {"dinamica", "smartwatch", "relogio"},
    "equilibrio": {"mascara", "acidificante", "ph"},
    "acao": {"mascara", "acidificante"},
    "apara": {"descascador", "legumes"},
    "casca": {"descascador", "legumes"},
    "integrado": {"gps", "radio", "autoradio"},
    "integrada": {"gps", "radio", "autoradio"},
    "leveza": {"leve", "sandalia"},
    "acessorios": {"pinceis", "maquiagem", "joias"},
    "facial": {"gel", "limpeza"},
    "bordas": {"costura", "laser"},
    "temperatura": {"quente", "quentes", "fria", "frias", "termico"},
    "termicamente": {"termico", "quente", "frio"},
    "thermal": {"protetor", "termico"},
    # Narrow semantic equivalents from captions explicitly approved by the
    # project owner. These stay tied to their confirmed product facts.
    "facilidade": {"descascador", "legumes"},
    "descascagem": {"descascador", "legumes"},
    "divisao": {"compartimento", "almoco"},
    "refeicao": {"almoco", "compartimento"},
    "visor": {"display", "digital"},
    "comprimento": {"midi"},
    "esfoliacao": {"esfoliante", "corporal"},
}


@dataclass(frozen=True)
class CaptionNormalization:
    caption: str
    corrections: tuple[str, ...]


class CaptionPolicyError(ValueError):
    pass


def _fold(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in value if not unicodedata.combining(ch)).casefold()


def _tokens(value: str, *, min_length: int = 4) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", _fold(value)) if len(token) >= min_length]


def _product_phrases(product_name: str) -> set[str]:
    tokens = [token for token in _tokens(product_name) if token not in PRODUCT_STOP_WORDS]
    phrases: set[str] = set()
    if len(tokens) == 2:
        phrases.add(" ".join(tokens))
    # A compact two-word category phrase can be the clearest accurate caption.
    # Reject copied short titles and three-token listing fragments, not short
    # category names drawn from richer Vision context.
    for size in (3,):
        for index in range(0, max(0, len(tokens) - size + 1)):
            phrases.add(" ".join(tokens[index:index + size]))
    return phrases


def _hashtag_sequences(product_name: str) -> set[str]:
    tokens = [token for token in _tokens(product_name) if token not in PRODUCT_STOP_WORDS]
    sequences: set[str] = set()
    for size in range(2, min(3, len(tokens)) + 1):
        for index in range(0, len(tokens) - size + 1):
            sequences.add("".join(tokens[index:index + size]))
    return sequences


def _brand_model_tokens(context: dict[str, Any] | None) -> set[str]:
    if not context:
        return set()
    leaked: set[str] = set()
    # Uppercase seller styling is not enough to make common function words or
    # product details look like a brand/model (for example, "NO STRASS").
    ordinary_uppercase_product_terms = set(PRODUCT_STOP_WORDS) | {
        "bojo", "foro", "kit", "strass", "verao", "inverno", "outono",
        "primavera", "amoled", "oled", "uhd", "tv", "led", "usb", "bpa", "abs",
        "cm", "mm", "gb", "mb", "fps", "spf", "pa", "pvc", "bb", "salto",
        "cozinha", "colecao", "tematica", "trice", "matte", "cushion",
        "masculino", "masculina", "feminino", "feminina", "unissex",
        "inflavel", "pelos", "cachos", "palha", "casal", "inox", "ilhos",
        "preta", "maes", "madeira", "natal", "cruzadas", "termico", "retro",
        "curto", "treino", "bojo", "aco", "temperos", "tomadas", "silicone",
        "balcao", "plaquinha", "mdp", "porcelana", "personalizada", "capilar",
        "cordinha", "ramo", "ajustavel", "drenagem", "manga", "compras",
        "labial", "microfibra", "recarregavel", "dourado", "brasil", "bebe",
        "portatil", "mdf", "dupla", "face", "colorido", "estampa", "curta",
        "curtas", "longa", "longas", "branco", "branca", "vermelho", "vermelha",
        "azul", "roxo", "cristal", "alto", "relevo", "reutilizavel", "cobre",
        "leito", "brilhantes", "textura", "decorativa", "sabonete", "protetora",
        "matelado", "social", "esportiva", "menino", "menina", "suedine",
        "rasteirinha", "percal", "termica", "cobre", "inoxidavel", "canguru",
        "bandeira", "estampada", "gourmet", "capsula", "duplex", "inverter",
        "texto", "disco", "manga", "compras", "bebe", "pêlos", "drenagem",
        "bêbê", "mães", "cachos", "microfibra", "ramo", "palha",
        "eletrico", "eletrica", "automatico", "automatica",
    } | set(_KNOWN_PRODUCT_HEAD_TERMS)
    for key in ("brand", "brandName"):
        value = context.get(key)
        if value:
            leaked.update(_tokens(str(value)))
    for key in ("model", "modelName"):
        value = context.get(key)
        if value:
            for token in re.findall(r"[a-z0-9]+", _fold(str(value))):
                if len(token) >= 2:
                    leaked.add(token)
    # Stylized casing such as "GiGiL" and all-caps product codes are strong
    # identity signals even when the affiliate endpoint omits brand/model
    # fields. Do not infer identity from ordinary title position or Title Case.
    title = str(context.get("productName") or "")
    if not title.isupper():
        title_words = WORD_RE.findall(title)
        for token in title_words:
            if (
                len(token) >= 3
                and any(char.islower() for char in token)
                and any(char.isupper() for char in token[1:])
                and _fold(token) not in ordinary_uppercase_product_terms
            ) or (
                len(token) >= 2
                and token.isupper()
                and token.isalpha()
                and _fold(token) not in ordinary_uppercase_product_terms
            ):
                leaked.add(_fold(token))
        # Marketplace titles often append a brand after the word "original"
        # and place a model year between a franchise or model name and its
        # style suffix (for example, "Hawkins 1983 Middle"). These names are
        # ordinary Title Case, so casing alone cannot identify them.
        for index, token in enumerate(title_words):
            if _fold(token) == "original" and index + 1 < len(title_words):
                following = title_words[index + 1]
                if (
                    len(following) >= 3
                    and following[:1].isupper()
                    and _fold(following) not in ordinary_uppercase_product_terms
                ):
                    leaked.add(_fold(following))
            if token.isdigit() and len(token) >= 4:
                for neighbor_index in (index - 1, index + 1):
                    if not 0 <= neighbor_index < len(title_words):
                        continue
                    neighbor = title_words[neighbor_index]
                    if (
                        len(neighbor) >= 3
                        and neighbor.isalpha()
                        and neighbor[:1].isupper()
                        and _fold(neighbor) not in ordinary_uppercase_product_terms
                        and _fold(neighbor) not in {
                            "verao", "inverno", "outono", "primavera",
                            "alto", "alta", "baixos", "baixas", "longo", "longa",
                            "curto", "curta", "medio", "media", "grande", "pequeno",
                            "pequena", "feminino", "feminina", "masculino", "masculina",
                        }
                    ):
                        leaked.add(_fold(neighbor))
        # A branded phrase in a marketplace title is often written as a
        # capitalized name joined to a second capitalized phrase by lowercase
        # Portuguese connectors ("Kokeshi o Milagre do Arroz"). Exclude only
        # runs with at least two such links; ordinary phrases like "Bolsa de
        # Ombro" do not meet that threshold.
        connectors = {"de", "do", "da", "dos", "das", "o", "a", "by"}
        generic_titlecase_terms = {
            "acessorio", "acessorios", "viagem", "banheiro", "decoracao",
        }
        for start in range(len(title_words)):
            index = start
            links = 0
            phrase: list[str] = []
            if not title_words[index][:1].isupper():
                continue
            phrase.append(title_words[index])
            while index + 2 < len(title_words):
                connector = title_words[index + 1]
                following = title_words[index + 2]
                if (
                    connector.casefold() not in connectors
                    or connector != connector.casefold()
                    or not following[:1].isupper()
                ):
                    break
                phrase.extend((connector, following))
                links += 1
                index += 2
            if links >= 2:
                known_phrase_terms = set(_KNOWN_PRODUCT_HEAD_TERMS) | ordinary_uppercase_product_terms | {
                    "cozinha", "sala", "quarto", "banheiro", "mesa", "casa",
                    "tematica", "colecao", "sofa",
                }
                # Keep only a suspected brand prefix before the first known
                # product or ordinary detail. This preserves cases such as
                # "Kokeshi o Milagre do Arroz" while avoiding false brand
                # flags on phrases like "Conjunto de Facas de Cozinha".
                known_position = next(
                    (index for index, token in enumerate(phrase)
                     if _fold(token) in known_phrase_terms),
                    len(phrase),
                )
                identity_prefix = phrase[:known_position]
                if identity_prefix:
                    leaked.update(
                        _fold(token) for token in identity_prefix
                        if token.casefold() not in connectors
                        and _fold(token) not in generic_titlecase_terms
                    )
    return leaked


def _possible_title_identity_tokens(context: dict[str, Any] | None) -> set[str]:
    """Keep ambiguous title prefixes out of generated vocabulary, not validation."""
    if not context or any(
        str(context.get(key) or "").strip()
        for key in ("brand", "brandName", "model", "modelName")
    ):
        return set()
    title_tokens = [
        token for token in _tokens(str(context.get("productName") or ""), min_length=3)
        if token not in PRODUCT_STOP_WORDS
    ]
    if len(title_tokens) < 2:
        return set()
    known_types = set(_KNOWN_PRODUCT_HEAD_TERMS) | {
        "calcado", "calcados", "chinelo", "sandalia", "sapato", "scarpin",
        "smartwatch", "relogio", "vestuario", "organizador", "descascador",
        "escova", "calcinha", "tanga", "legumes", "vestido", "pijama",
    }
    if title_tokens[0] in known_types:
        return set()
    category_tokens: set[str] = set()
    for key in ("category", "categoryName", "productCategory", "productType"):
        category_tokens.update(_tokens(str(context.get(key) or ""), min_length=3))
    # If the category identifies the second title token as the product noun,
    # treat only the first word as ambiguous (e.g. "Moderna Caneca").
    prefix_size = 1 if category_tokens & set(title_tokens[1:3]) else 2
    return set(title_tokens[:prefix_size])


def _vision_contains_literal_term(
    term: str,
    *,
    product_name: str = "",
    product_context: dict[str, Any] | None = None,
) -> bool:
    values = [str(product_name or "")]

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                values.append(str(key))
                collect(nested)
        elif isinstance(value, (list, tuple, set)):
            for nested in value:
                collect(nested)
        elif value not in (None, ""):
            values.append(str(value))

    if product_context:
        for key in (
            "productName", "category", "categoryName", "productCategory", "productType",
            "description", "attributes", "technicalCharacteristics", "usage", "useCase",
            "style", "appearance", "__vision_confirmed_facts",
        ):
            collect(product_context.get(key))
    folded = _fold(" ".join(values))
    return bool(re.search(rf"\b{re.escape(_fold(term))}\b", folded))


def _commercial_or_package_match(
    text: str,
    *,
    product_name: str = "",
    product_context: dict[str, Any] | None = None,
) -> str | None:
    folded = _fold(text)
    for word in FORBIDDEN_WORDS:
        if re.search(rf"\b{re.escape(_fold(word))}\b", folded):
            # "Tampa" is often a real product feature (for example, a lid
            # with a lock). Keep it blocked unless Vision explicitly confirms it.
            if word == "tampa" and _vision_contains_literal_term(
                word, product_name=product_name, product_context=product_context,
            ):
                continue
            return f"palavra proibida: {word}"
    for word in SALES_WORDS:
        folded_word = _fold(word)
        if re.search(rf"(?<![a-z0-9]){re.escape(folded_word)}(?![a-z0-9])", folded):
            return f"linguagem comercial proibida: {word}"
    for phrase in SALES_PHRASES:
        if re.search(rf"(?<![a-z0-9]){re.escape(_fold(phrase))}(?![a-z0-9])", folded):
            return f"chamada comercial proibida: {phrase}"
    return None


def _technical_leak(text: str) -> bool:
    folded = _fold(text)
    pattern = r"\b\d+(?:[\.,]\d+)?\s?(?:ml|l|litros?|cm|mm|m|kg|g|v|volts?|w|watts?)\b"
    technical_terms = r"\b(?:ph|voltagem|especifica(?:cao|coes))\b"
    clothing_sizes = r"\b(?:do\s+|de\s+)?(?:pp|p|m|g|gg|xg|eg|egg)\s+(?:ao|a)\s*(?:pp|p|m|g|gg|xg|eg|egg)\b"
    return bool(
        re.search(pattern, folded)
        or re.search(technical_terms, folded)
        or re.search(clothing_sizes, folded)
    )


def _has_single_character_product_head_typo(
    words: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    """Catch likely one-letter misspellings of a Vision-confirmed category."""
    exact_context = _context_tokens(product_name, product_context)
    heads = caption_product_anchor_terms(product_context, product_name=product_name)
    for raw in words:
        candidate = _fold(raw)
        if len(candidate) < 5 or candidate in exact_context:
            continue
        for head in heads:
            expected = _fold(head)
            if len(expected) < 5 or len(candidate) != len(expected):
                continue
            if sum(left != right for left, right in zip(candidate, expected)) == 1:
                return True
    return False


def _context_tokens(product_name: str, product_context: dict[str, Any] | None) -> set[str]:
    values = [str(product_name or "")]
    if product_context:
        values.extend(
            str(product_context.get(key) or "")
            for key in _CONTEXT_FIELDS
            if product_context.get(key) not in (None, "", [], {})
        )
    excluded = _brand_model_tokens(product_context)
    tokens: set[str] = set()
    for value in values:
        tokens.update(
            token for token in _tokens(value, min_length=3)
            if token not in excluded and token not in PRODUCT_STOP_WORDS
        )
    return tokens


def _context_token_stems(token: str) -> set[str]:
    """Match common Portuguese singular/plural and gender inflections safely."""
    value = str(token)
    variants = {value}
    # Common Portuguese plural classes must match the singular Vision title:
    # coração/corações, pão/pães, animal/animais, papel/papéis, farol/faróis.
    for plural_ending, singular_ending in (
        ("oes", "ao"), ("aes", "ao"), ("ais", "al"),
        ("eis", "el"), ("ois", "ol"),
    ):
        if len(value) > len(plural_ending) + 2 and value.endswith(plural_ending):
            variants.add(value[:-len(plural_ending)] + singular_ending)
    if len(value) >= 5 and value.endswith("s"):
        variants.add(value[:-1])
    if len(value) >= 5 and value.endswith(("a", "o", "e")):
        variants.add(value[:-1])
    return variants


def caption_product_anchor_terms(
    product_context: dict[str, Any] | None,
    *,
    product_name: str = "",
) -> tuple[str, ...]:
    """Return the category/head terms a short caption should identify.

    Vision's legacy records often contain only a product title plus IDs,
    ratings, and an image URL. In that sparse case, the first meaningful title
    term is the safest available product identity. Rich descriptions or usage
    evidence can support a contextual reaction without forcing title wording.
    """
    context = product_context or {}
    rich_fields = ("description", "usage", "useCase", "appearance", "attributes")
    if any(str(context.get(key) or "").strip() for key in rich_fields):
        return ()

    category_terms: list[str] = []
    for key in _CATEGORY_FIELDS:
        for token in _tokens(str(context.get(key) or ""), min_length=3):
            if (
                token not in PRODUCT_STOP_WORDS
                and token not in _GENERIC_HASHTAGS
                and len(token) >= 3
            ):
                category_terms.append(token)
    title = str(product_name or context.get("productName") or "")
    excluded = _brand_model_tokens(context)
    title_tokens = [
        token for token in _tokens(title, min_length=3)
        if token not in PRODUCT_STOP_WORDS and len(token) >= 3
    ]
    product_terms = [
        token for token in title_tokens
        if token in _KNOWN_PRODUCT_HEAD_TERMS and token not in _GENERIC_HASHTAGS
    ]
    # When Vision has no explicit category field, use the first known product
    # head as the required category anchor. Later title terms may be a material,
    # feature, model or collection name and cannot substitute for category.
    return tuple(dict.fromkeys((*category_terms, *product_terms[:1])))


def _caption_product_category_terms(
    product_name: str,
    product_context: dict[str, Any] | None,
) -> set[str]:
    """Identify the item noun that must stay out of the caption body."""
    context = product_context or {}
    rule_category = str(context.get("__title_rule_category") or "").strip()
    if _has_title_rule_evidence(
        WORD_RE.findall(str(context.get("__title_rule_caption_main") or "")),
        context,
    ) and rule_category:
        return {_fold(rule_category)}
    # A few Portuguese product classes are only two letters long after accent
    # folding (pá, pó). Keep the match bounded to the explicit category set so
    # short connector words never become product categories.
    title_tokens = _tokens(product_name or str(context.get("productName") or ""), min_length=2)
    raw_title = product_name or str(context.get("productName") or "")
    # In seller titles, "jogo de X" names a set of X items; X is the useful
    # product category for captions (jogo de lençol, jogo de toalhas, etc.).
    for index in range(len(title_tokens) - 2):
        if title_tokens[index] == "jogo" and title_tokens[index + 1] == "de":
            member = next(
                (token for token in title_tokens[index + 2:] if token in _KNOWN_PRODUCT_HEAD_TERMS),
                None,
            )
            if member:
                return {member}
    primary = next(
        (
            token for token in title_tokens
            if token in _KNOWN_PRODUCT_HEAD_TERMS
            and not (
                token == "pa"
                and not re.search(r"\bpá\b|\bpa\s+(?:de\s+)?(?:jardim|terra|a[cç]o|lixo|constru[cç][aã]o)\b", raw_title, re.IGNORECASE)
            )
        ),
        None,
    )
    if primary:
        return {primary}

    # Use a Vision category only when the product title has no recognizable
    # product noun. Broad categories such as "café" describe the contents or
    # use of a cup and should not be mistaken for the cup itself.
    for key in ("category", "productCategory", "productType", "categoryName"):
        field_terms = set(_tokens(str(context.get(key) or ""), min_length=3))
        recognized = field_terms & _KNOWN_PRODUCT_HEAD_TERMS
        if recognized:
            return recognized
    return set()


def _has_title_rule_evidence(
    words: list[str], product_context: dict[str, Any] | None,
) -> bool:
    """Confirm selector-attached evidence for this exact deterministic phrase."""
    context = product_context or {}
    expected = str(context.get("__title_rule_caption_main") or "").strip()
    facts = context.get("__title_rule_facts")
    if not expected or not isinstance(facts, (list, tuple)) or not facts:
        return False
    actual_key = " ".join(_fold(word) for word in words)
    expected_key = " ".join(_fold(word) for word in WORD_RE.findall(expected))
    return bool(expected_key) and actual_key == expected_key


def caption_product_category_terms(
    product_name: str,
    product_context: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    """Expose the product noun for prompt context and category-safe generation."""
    return tuple(sorted(_caption_product_category_terms(product_name, product_context)))


def _caption_mentions_product_category(
    words: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    categories = _caption_product_category_terms(product_name, product_context)
    stems = set().union(*(_context_token_stems(term) for term in categories)) if categories else set()
    return any(
        _fold(word) in categories
        or bool(_context_token_stems(_fold(word)) & stems)
        for word in words
    )


def _category_has_confirmed_caption_detail(
    words: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    """Allow a product name when the caption also states a Vision-backed fact."""
    if _has_title_rule_evidence(words, product_context):
        return True
    categories = _caption_product_category_terms(product_name, product_context)
    category_stems = set().union(
        *(_context_token_stems(term) for term in categories)
    ) if categories else set()
    context = dict(product_context or {})
    if product_name and not context.get("productName"):
        context["productName"] = product_name
    from .grounded import extract_vision_caption_facts

    fact_tokens = {
        _fold(token)
        for token in WORD_RE.findall(" ".join(extract_vision_caption_facts(context)))
    }
    fact_stems = set().union(
        *(_context_token_stems(token) for token in fact_tokens)
    ) if fact_tokens else set()
    natural_links = {
        "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos",
        "em", "na", "nas", "no", "nos", "para", "por", "pra", "pro",
        "tipo", "como", "parece", "parecem", "ate", "um", "uma", "o", "os",
    }
    category_positions = [
        index for index, word in enumerate(words)
        if _fold(word) in category_stems
        or bool(_context_token_stems(_fold(word)) & category_stems)
    ]
    if any(
        index > 0 and _fold(words[index - 1]) not in natural_links
        for index in category_positions
    ):
        return False
    return any(
        _fold(word) not in category_stems
        and bool(_context_token_stems(_fold(word)) & fact_stems)
        for word in words
    )


def _caption_uses_unconfirmed_spatial_relation(
    words: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    """Reject a location claim that connects separate, unrelated Vision facts."""
    product_part_terms = {
        "alca", "alcas", "base", "bico", "bolso", "bolsos", "borda",
        "cabedal", "cabo", "capa", "capuz", "costas", "display", "forro",
        "frente", "gola", "lateral", "laterais", "manga", "mangas", "ombro",
        "ombros", "ponta", "pontas", "punho", "punhos", "sola", "solado",
        "superficie", "tampa", "tela", "topo", "traseira", "visor",
    }
    spatial_links = {"na", "no", "nas", "nos", "sobre", "sob"}
    folded_words = [_fold(word) for word in words]
    location_pairs = [
        (folded_words[index - 1], link, folded_words[index + 1])
        for index, link in enumerate(folded_words)
        if link in spatial_links and 0 < index < len(folded_words) - 1
    ]
    if not location_pairs:
        return False

    context = dict(product_context or {})
    if product_name and not context.get("productName"):
        context["productName"] = product_name
    from .grounded import extract_vision_caption_facts

    facts = extract_vision_caption_facts(context)
    fact_terms = [
        {_fold(token) for token in WORD_RE.findall(fact)}
        for fact in facts
    ]
    fact_stems = [
        set().union(*(_context_token_stems(term) for term in terms))
        for terms in fact_terms
        if terms
    ]
    categories = {
        _fold(term)
        for term in _caption_product_category_terms(product_name, context)
    }
    supported_tokens = _vision_fact_tokens(product_name, context)
    supported_stems = set().union(
        *(_context_token_stems(token) for token in supported_tokens)
    ) if supported_tokens else set()
    source_values: list[str] = [str(context.get("productName") or "")]

    def flatten(value: Any) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                flatten(nested)
        elif isinstance(value, (list, tuple, set)):
            for nested in value:
                flatten(nested)
        elif value not in (None, ""):
            source_values.append(str(value))

    for key in (
        "category", "categoryName", "productCategory", "productType",
        "description", "attributes", "technicalCharacteristics",
        "usage", "useCase", "style", "appearance",
    ):
        flatten(context.get(key))
    source_text = _fold(" ".join(source_values))

    for left, link, right in location_pairs:
        # Usage and time phrases such as "no banho" are natural editorial
        # context, not claims that one product feature is physically attached
        # to another. Check only product components and surfaces here.
        if right not in product_part_terms:
            continue
        # Let ordinary grounding reject unsupported filler such as "design".
        # This check is for two Vision-backed attributes the model may have
        # incorrectly connected to each other.
        if not (
            _context_token_stems(left) & supported_stems
            and _context_token_stems(right) & supported_stems
        ):
            continue
        literal_relation = re.search(
            rf"\b{re.escape(left)}\s+{re.escape(link)}\s+{re.escape(right)}\b",
            source_text,
        )
        left_stems = _context_token_stems(left)
        right_stems = _context_token_stems(right)
        same_fact = any(
            bool(left_stems & stems) and bool(right_stems & stems)
            for stems in fact_stems
        )
        natural_product_reference = (
            right in categories
            and bool(_context_token_stems(left) & {
                stem
                for token in supported_tokens
                for stem in _context_token_stems(token)
            })
        )
        if not literal_relation and not same_fact and not natural_product_reference:
            return True
    return False


def _caption_repeats_title_category_fragment(
    words: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    """Reject a listing-like category+detail pair copied straight from Vision."""
    if _has_title_rule_evidence(words, product_context):
        return False
    categories = _caption_product_category_terms(product_name, product_context)
    if not categories:
        return False
    main_tokens = [
        _fold(word) for word in words
        if _fold(word) not in PRODUCT_STOP_WORDS
    ]
    phrase_tokens = [_fold(word) for word in words]
    title_tokens = [
        _fold(word) for word in WORD_RE.findall(product_name or str((product_context or {}).get("productName") or ""))
        if _fold(word) not in PRODUCT_STOP_WORDS
    ]
    if len(main_tokens) < 2:
        return False

    # A bare category/material pair is still a listing fragment even when
    # another seller adjective separates those words in the title (for
    # example, "Sutiã microfibra"). A material followed by "em" and the
    # garment name reverses the normal Portuguese relationship and reads
    # like extracted keywords rather than an editorial caption.
    material_terms = {
        "algodao", "acrilico", "aco", "camurca", "ceramica", "couro",
        "elastano", "inox", "la", "madeira", "microfibra", "moletinho",
        "nylon", "poliester", "plastico", "silicone", "suede", "suplex",
        "trico", "tricot", "viscose", "vidro",
    }
    body_positions = [
        (index, token) for index, token in enumerate(main_tokens)
    ]
    for index, token in body_positions:
        if token in material_terms and any(
            later in categories for later in main_tokens[index + 1:]
        ):
            # "Algodão em moletom" reverses "moletom de algodão".
            if "em" in phrase_tokens and any(
                later in categories for later in main_tokens[index + 1:]
            ):
                return True
            if index == 0 and main_tokens[1] in categories:
                return True

    if any(token in categories for token in main_tokens[:2]) and any(
        token in material_terms for token in main_tokens[:3]
    ):
        category_position = next(
            index for index, token in enumerate(phrase_tokens)
            if token in categories
        )
        material_position = next(
            index for index, token in enumerate(phrase_tokens)
            if token in material_terms
        )
        natural_material_link = (
            category_position < material_position
            and phrase_tokens[category_position + 1:material_position]
            in (["de"], ["do"], ["da"], ["dos"], ["das"])
        )
        if not natural_material_link:
            return True

    return any(
        main_tokens[index] in categories
        and title_tokens[position:position + 2] == main_tokens[index:index + 2]
        for index in range(len(main_tokens) - 1)
        for position in range(max(0, len(title_tokens) - 1))
    )


def _caption_is_title_keyword_list(
    words: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    """Reject multiword title fragments that read like a compact listing."""
    if _has_title_rule_evidence(words, product_context):
        return False
    folded = [_fold(word) for word in words]
    if folded and folded[0] in {"kit", "conjunto"}:
        return True
    title = product_name or str((product_context or {}).get("productName") or "")
    title_tokens = [
        _fold(word) for word in WORD_RE.findall(title)
        if _fold(word) not in PRODUCT_STOP_WORDS
    ]
    body_tokens = [word for word in folded if word not in PRODUCT_STOP_WORDS]
    if len(body_tokens) < 3 or not title_tokens:
        return False
    title_stems = set().union(*(_context_token_stems(token) for token in title_tokens))
    all_from_title = all(
        bool(_context_token_stems(token) & title_stems)
        for token in body_tokens
    )
    if not all_from_title:
        return False
    # A noun/adjective sequence is a catalog fragment. A natural preposition
    # or comparison can express a relation between those same verified facts.
    relation_words = {
        "com", "da", "das", "de", "do", "dos",
        "em", "na", "nas", "no", "nos", "para", "por", "como", "tipo",
        "parece", "lembra",
    }
    return not bool(set(folded) & relation_words)


def _main_phrase_has_product_anchor(
    words: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    anchors = set(caption_product_anchor_terms(
        product_context, product_name=product_name,
    ))
    if not anchors:
        return True

    expanded = set(anchors)
    for term, related in _MAIN_CONTEXT_ALIASES.items():
        if term in anchors:
            expanded.update(related)
        if related & anchors:
            expanded.add(term)

    def stem(token: str) -> str:
        return token[:-1] if len(token) >= 5 and token.endswith(("a", "o", "e", "s")) else token

    expanded_stems = {stem(token) for token in expanded}
    return any(
        _fold(word) in expanded or stem(_fold(word)) in expanded_stems
        for word in words
    )


def _hashtags_have_product_anchor(
    hashtags: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
    words: list[str] | None = None,
) -> bool:
    # A factual attribute can support the sentence without identifying the
    # product. Require one hashtag for the primary product head whenever the
    # title or Vision category gives us a known head (e.g. #pantufa, not
    # #chinelo for a pantufa and not #cano for meias).
    product_heads = _caption_product_category_terms(product_name, product_context)
    if product_heads:
        head_stems = set().union(
            *(_context_token_stems(head) for head in product_heads)
        )
        has_category_hashtag = any(
            bool(_context_token_stems(_fold(raw_tag)) & head_stems)
            for raw_tag in hashtags
        )
        if not has_category_hashtag:
            # A hashtag for a Vision-confirmed use or attribute is also a
            # meaningful product anchor when the caption itself talks about
            # that same fact (for example, "Café quentinho #café" for a cup
            # explicitly titled for coffee). This keeps the hashtag useful
            # without allowing an unrelated trend tag.
            main_stems = set().union(*(
                _context_token_stems(_fold(word))
                for word in (words or ())
                if _fold(word) not in PRODUCT_STOP_WORDS
            )) if words else set()
            fact_tokens = _vision_fact_tokens(product_name, product_context)
            fact_stems = set().union(*(
                _context_token_stems(token) for token in fact_tokens
            )) if fact_tokens else set()
            category_context = product_context or {}
            category_tokens = {
                token
                for key in _CATEGORY_FIELDS
                for token in _tokens(str(category_context.get(key) or ""), min_length=3)
            }
            category_stems = set().union(*(
                _context_token_stems(token) for token in category_tokens
            )) if category_tokens else set()
            grounded_tag = any(
                hashtag_context_score(
                    raw_tag,
                    product_name=product_name,
                    product_context=product_context,
                ) > 0
                and (
                    bool(
                        _context_token_stems(_fold(raw_tag))
                        & main_stems
                        & fact_stems
                    )
                    or bool(
                        _context_token_stems(_fold(raw_tag))
                        & category_stems
                    )
                )
                for raw_tag in hashtags
            )
            if not grounded_tag:
                return False

    anchors = {
        _fold(term)
        for term in caption_product_anchor_terms(
            product_context, product_name=product_name,
        )
    }
    fact_tokens = _vision_fact_tokens(product_name, product_context)
    fact_stems = set().union(
        *(_context_token_stems(token) for token in fact_tokens)
    ) if fact_tokens else set()
    if not anchors:
        return any(
            _fold(raw_tag) in fact_tokens
            or any(
                _context_token_stems(token) & fact_stems
                for token in re.findall(r"[a-z0-9]+", _fold(raw_tag))
            )
            or bool(
                _HASHTAG_CONTEXT_ALIASES.get(_fold(raw_tag), set())
                & fact_tokens
            )
            for raw_tag in hashtags
        ) or not fact_tokens
    for raw_tag in hashtags:
        tag = _fold(raw_tag)
        if tag in anchors:
            return True
        tag_tokens = re.findall(r"[a-z0-9]+", tag)
        if tag in fact_tokens or any(
            _context_token_stems(token) & fact_stems for token in tag_tokens
        ):
            return True
        aliases = _HASHTAG_CONTEXT_ALIASES.get(tag)
        if not aliases and tag.endswith("s"):
            aliases = _HASHTAG_CONTEXT_ALIASES.get(tag[:-1])
        if aliases and aliases & anchors:
            return True
    return False


def _is_incomplete_article_label(words: list[str]) -> bool:
    """Reject article-led noun labels with no predicate (e.g. 'O display digital')."""
    if not words or _fold(words[0]) not in {"o", "a", "os", "as"}:
        return False
    predicate_words = {
        "e", "sao", "tem", "têm", "fica", "ficam", "vem", "vêm",
        "acompanha", "acompanham", "parece", "parecem", "traz", "trazem",
        "aparece", "aparecem", "mostra", "mostram", "serve", "servem",
        "pode", "podem", "permite", "permitem", "merece", "merecem",
    }
    return not any(_fold(word) in predicate_words for word in words[1:])


def _secondary_product_noun_is_comparative(
    words: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    """Require an explicit comparison before using a secondary product noun."""
    title_nouns = set(_tokens(product_name)) & _COMPARATIVE_TITLE_NOUNS
    primary = set()
    for token in _tokens(product_name):
        if token in _KNOWN_PRODUCT_HEAD_TERMS or token in _GENDERED_PRODUCT_NOUNS:
            primary.add(token)
            break
    secondary = title_nouns - primary
    caption_nouns = {_fold(word) for word in words} & secondary
    if not caption_nouns:
        return True
    for noun in caption_nouns:
        noun_index = next(index for index, word in enumerate(words) if _fold(word) == noun)
        if not any(_fold(word) in _COMPARISON_MARKERS for word in words[:noun_index]):
            # A Vision title can explicitly describe a component or pairing
            # with "com"/"para". Preserve that relation in the caption rather
            # than forcing every second noun into a simile.
            primary_word = next(
                (_fold(word) for word in words[:noun_index]
                 if _fold(word) in _KNOWN_PRODUCT_HEAD_TERMS),
                None,
            )
            title_words = [_fold(word) for word in WORD_RE.findall(product_name)]
            try:
                primary_index = title_words.index(primary_word) if primary_word else -1
                title_noun_index = title_words.index(noun, primary_index + 1)
            except ValueError:
                return False
            caption_links = {_fold(word) for word in words[:noun_index]}
            title_links = set(title_words[primary_index + 1:title_noun_index])
            if not ({"com", "para", "e", "tipo"} & caption_links & title_links):
                return False
    return True


def _main_phrase_is_contextual(
    words: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    if _has_title_rule_evidence(words, product_context):
        return True
    context = _vision_fact_tokens(product_name, product_context)
    context_stems = set().union(*(_context_token_stems(value) for value in context)) if context else set()
    grounded = False
    for raw in words:
        token = _fold(raw)
        if token in PRODUCT_STOP_WORDS:
            continue
        stem = token[:-1] if len(token) >= 5 and token[-1:] in {"a", "o", "e", "s"} else token
        if token in context or _context_token_stems(token) & context_stems:
            grounded = True
            continue
        if len(token) < 3:
            if token in _NEUTRAL_REACTION_WORDS:
                continue
            return False
        if (_MAIN_CONTEXT_ALIASES.get(token, set()) | _MAIN_CONTEXT_ALIASES.get(stem, set())) & context:
            grounded = True
            continue
        if token in _NEUTRAL_REACTION_WORDS or (
            token.endswith("s") and token[:-1] in _NEUTRAL_REACTION_WORDS
        ):
            continue
        return False
    return grounded


def _vision_fact_tokens(
    product_name: str,
    product_context: dict[str, Any] | None,
) -> set[str]:
    """Validate claims against Vision facts and safe semantic terms in its title."""
    context = dict(product_context or {})
    if product_name and not context.get("productName"):
        context["productName"] = product_name
    provided = context.get("__vision_confirmed_facts")
    facts = tuple(
        str(value).strip()
        for value in provided
        if str(value).strip()
    ) if isinstance(provided, (list, tuple, set)) else ()
    rule_facts = context.get("__title_rule_facts")
    if _has_title_rule_evidence(
        WORD_RE.findall(str(context.get("__title_rule_caption_main") or "")),
        context,
    ) and isinstance(rule_facts, (list, tuple)):
        facts = (*facts, *(str(value).strip() for value in rule_facts if str(value).strip()))
    if not facts:
        # Import lazily because grounded.py imports the Policy helpers above.
        from .grounded import extract_vision_caption_facts

        facts = extract_vision_caption_facts(context)
    fact_tokens = {
        token for token in _tokens(" ".join(facts), min_length=2)
        if token not in PRODUCT_STOP_WORDS
        and _fold(token) not in _VISION_UNTRUSTED_CLAIM_WORDS
        and not _technical_leak(token)
    }
    # Structured Vision fields (description, attributes, usage, etc.) are
    # trusted evidence. Keep their concrete words, while dropping seller-style
    # promises and commercial adjectives.
    structured_values: list[str] = []
    for key in _CONTEXT_FIELDS:
        if key == "productName":
            continue
        value = context.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict):
            structured_values.extend(
                f"{name} {detail}"
                for name, detail in value.items()
                if str(name).strip() and detail not in (None, "", [], {})
            )
        elif isinstance(value, (list, tuple, set)):
            structured_values.extend(str(item) for item in value if str(item).strip())
        else:
            structured_values.append(str(value))
    for token in _tokens(" ".join(structured_values), min_length=2):
        folded = _fold(token)
        if (
            token in PRODUCT_STOP_WORDS
            or folded in _VISION_UNTRUSTED_CLAIM_WORDS
            or _commercial_or_package_match(
                token, product_name=product_name, product_context=product_context,
            )
            or any(char.isdigit() for char in token)
        ):
            continue
        fact_tokens.add(token)
    # Product titles are noisy seller copy. Only facts extracted from the title
    # and the recognized product head are evidence here; accepting every title
    # word let brand/line names such as "Ox Nutre" leak into captions.
    fact_tokens.update(
        token for token in caption_product_anchor_terms(
            context, product_name=product_name,
        )
        if token not in PRODUCT_STOP_WORDS
        and _fold(token) not in _VISION_UNTRUSTED_CLAIM_WORDS
    )
    # Vision's structured category fields are a second trusted source for
    # short editorial wording and relevant tags.
    category_text = " ".join(
        str(context.get(key) or "")
        for key in _CATEGORY_FIELDS
        if context.get(key) not in (None, "", [], {})
    )
    fact_tokens.update(
        token for token in _tokens(category_text, min_length=2)
        if token not in PRODUCT_STOP_WORDS
    )
    title_head = next(
        (
            token for token in _tokens(product_name, min_length=3)
            if token in _KNOWN_PRODUCT_HEAD_TERMS
        ),
        None,
    )
    if title_head:
        fact_tokens.add(title_head)
    return fact_tokens


def _has_known_agreement_error(words: list[str]) -> bool:
    """Reject clear article/adjective agreement errors in grounded nouns."""
    articles = {
        "um": ("m", "s"), "uma": ("f", "s"),
        "uns": ("m", "p"), "umas": ("f", "p"),
        "o": ("m", "s"), "a": ("f", "s"),
        "os": ("m", "p"), "as": ("f", "p"),
        "no": ("m", "s"), "na": ("f", "s"),
        "nos": ("m", "p"), "nas": ("f", "p"),
        "do": ("m", "s"), "da": ("f", "s"),
        "dos": ("m", "p"), "das": ("f", "p"),
        "ao": ("m", "s"), "aos": ("m", "p"),
    }
    nouns = [
        (index, _GENDERED_PRODUCT_NOUNS[_fold(word)])
        for index, word in enumerate(words)
        if _fold(word) in _GENDERED_PRODUCT_NOUNS
    ]
    for article_index, word in enumerate(words):
        article = articles.get(_fold(word))
        if article is None:
            continue
        following = [
            (index, noun)
            for index, noun in nouns
            if article_index < index <= article_index + 3
        ]
        if following and min(following, key=lambda value: value[0])[1] != article:
            return True
    adjectives = [
        (index, _GENDERED_REACTION_ADJECTIVES[_fold(word)])
        for index, word in enumerate(words)
        if _fold(word) in _GENDERED_REACTION_ADJECTIVES
    ]
    for adjective_index, adjective in adjectives:
        if not nouns:
            continue
        _noun_index, noun = min(nouns, key=lambda candidate: abs(candidate[0] - adjective_index))
        if (adjective[0] != "x" and adjective[0] != noun[0]) or (
            noun[1] is not None and adjective[1] != noun[1]
        ):
            return True
    return False


def _has_unlinked_product_nouns(words: list[str]) -> bool:
    """Reject a string of product nouns with no natural relation between them."""
    noun_positions = [
        index for index, word in enumerate(words)
        if _fold(word) in _GENDERED_PRODUCT_NOUNS
    ]
    if len(noun_positions) < 2:
        return False
    for left, right in zip(noun_positions, noun_positions[1:]):
        if not any(_fold(word) in PRODUCT_STOP_WORDS for word in words[left + 1:right]):
            return True
    return False


def _has_vague_trailing_filler(text: str) -> bool:
    """Reject empty closers that make an otherwise grounded fragment sound awkward."""
    folded = _fold(text)
    if re.search(r"\b(?:em\s+foco|em\s+destaque)\b[.!?]*$", folded):
        return True
    if re.search(r"(?:,\s*)?\b(?:so|apenas)\s+isso\b[.!?]*$", folded):
        return True
    if re.search(
        r"\b(?:a|as|ao|aos|da|das|de|do|dos|e|em|na|nas|no|nos|para|por|pra|pro|o|os|um|uma|aqui|ai)\b[.!?]*$",
        folded,
    ):
        return True
    # Reject incomplete generated fragments such as "Listras duplas na
    # lateral são". These predicates need a complement to form a natural
    # caption; the check applies only at the end of the main phrase.
    return bool(re.search(
        r"\b(?:sao|e|esta|estao|tem|vem|fica|ficam|pode|podem|parece|parecem|lembra|acompanha|acompanham|oferece|oferecem|traz|trazem|permite|permitem|deixa|deixam|garante|garantem)\b[.!?]*$",
        folded,
    ))


def _has_unnatural_bag_device_relation(words: list[str]) -> bool:
    """Reject a literal ``bag de computer`` construction in Brazilian Portuguese."""
    folded = [_fold(word) for word in words]
    bags = {"bolsa", "bolsas", "mochila", "mochilas", "pasta", "pastas"}
    devices = {"computador", "computadores", "notebook", "notebooks", "laptop", "laptops", "tablet", "tablets"}
    return any(
        folded[index] in bags
        and index + 2 < len(folded)
        and folded[index + 1] == "de"
        and folded[index + 2] in devices
        for index in range(len(folded))
    )


def _normalize_known_agreement(text: str) -> tuple[str, bool]:
    """Safely inflect a known reaction adjective to match its product noun."""
    matches = list(WORD_RE.finditer(text))
    words = [match.group(0) for match in matches]
    nouns = [
        (index, _GENDERED_PRODUCT_NOUNS[_fold(word)])
        for index, word in enumerate(words)
        if _fold(word) in _GENDERED_PRODUCT_NOUNS
    ]
    if not nouns:
        return text, False

    replacements: list[tuple[int, int, str]] = []
    for adjective_index, word in enumerate(words):
        folded = _fold(word)
        base = _REACTION_ADJECTIVE_BASE.get(folded)
        if base is None:
            continue
        _noun_index, noun_form = min(
            nouns, key=lambda candidate: abs(candidate[0] - adjective_index),
        )
        adjective_number = _GENDERED_REACTION_ADJECTIVES[folded][1]
        desired = _REACTION_ADJECTIVE_PARADIGMS[base].get(
            (noun_form[0], noun_form[1] or adjective_number),
        )
        if desired is not None and desired != folded:
            match = matches[adjective_index]
            # Keep initial capitalization while changing only a recognized
            # inflection; accent and semantic content are otherwise stable.
            if word[:1].isupper():
                desired = desired.capitalize()
            replacements.append((match.start(), match.end(), desired))

    if not replacements:
        return text, False
    corrected = text
    for start, end, replacement in reversed(replacements):
        corrected = corrected[:start] + replacement + corrected[end:]
    return corrected, True


def _normalize_context_spelling(
    text: str,
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> tuple[str, bool]:
    """Restore accents from Vision's own spelling without adding new words."""
    surfaces: dict[str, str] = {}
    for value in (product_name, *(
        str((product_context or {}).get(key) or "") for key in _CONTEXT_FIELDS
    )):
        for surface in WORD_RE.findall(str(value)):
            surfaces.setdefault(_fold(surface), surface)
    changed = False

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        original = match.group(0)
        # Vision titles often arrive without Portuguese diacritics. Preserve
        # correctly accented words supplied by the caption composer instead
        # of "correcting" them back to the marketplace's unaccented spelling.
        if _fold(original) != original.casefold():
            return original
        canonical = surfaces.get(_fold(original))
        if not canonical or canonical.casefold() == original.casefold():
            return original
        changed = True
        if original.isupper():
            return canonical.upper()
        if original[:1].isupper():
            return canonical[:1].upper() + canonical[1:]
        return canonical

    corrected = WORD_RE.sub(replace, text)
    return corrected, changed


def _normalize_sentence_case(text: str) -> tuple[str, bool]:
    matches = list(WORD_RE.finditer(text))
    replacements: list[tuple[int, int, str]] = []
    for index, match in enumerate(matches):
        original = match.group(0)
        if index == 0 or (original.isupper() and len(original) <= 4):
            continue
        lower = original.lower()
        if lower != original:
            replacements.append((match.start(), match.end(), lower))
    if not replacements:
        return text, False
    normalized = text
    for start, end, replacement in reversed(replacements):
        normalized = normalized[:start] + replacement + normalized[end:]
    return normalized, True


def hashtag_context_score(
    hashtag: str,
    *,
    product_name: str = "",
    product_context: dict[str, Any] | None = None,
) -> int:
    """Return positive only when the hashtag has persisted product-context support."""
    tag = _fold(str(hashtag or "").lstrip("#"))
    if tag == "diaadia":
        # The owner explicitly approved this lifestyle tag when paired with a
        # product-grounded tag (the full-caption validator enforces that anchor).
        return 1 if caption_product_anchor_terms(
            product_context, product_name=product_name,
        ) else 0
    tag_tokens = [token for token in re.findall(r"[a-z0-9]+", tag) if len(token) >= 3]
    if not tag_tokens or any(token in _GENERIC_HASHTAGS for token in tag_tokens):
        return 0
    context = _context_tokens(product_name, product_context)
    score = 0
    for token in tag_tokens:
        if token in context or any(
            len(token) >= 5
            and abs(len(token) - len(other)) <= 2
            and (token.startswith(other) or other.startswith(token))
            for other in context
        ):
            score += 2
            continue
        aliases = _HASHTAG_CONTEXT_ALIASES.get(token, set())
        if not aliases and token.endswith("s"):
            aliases = _HASHTAG_CONTEXT_ALIASES.get(token[:-1], set())
        if aliases & context:
            score += 1
            continue
        for alias, related in _HASHTAG_CONTEXT_ALIASES.items():
            if token == alias and related & context:
                score += 1
                break
    return score if score == len(tag_tokens) * 2 or score > 0 else 0


def caption_generation_vocabulary(
    product_context: dict[str, Any] | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return grounded text terms and hashtags safe to constrain an IA schema."""
    context = product_context or {}
    product_name = str(context.get("productName") or "")
    excluded = _brand_model_tokens(context) | _possible_title_identity_tokens(context)
    grounded: dict[str, str] = {}
    for key in _CONTEXT_FIELDS:
        value = context.get(key)
        if value in (None, "", [], {}):
            continue
        for surface in WORD_RE.findall(str(value)):
            folded = _fold(surface)
            if (
                len(folded) < 4
                or any(char.isdigit() for char in folded)
                or folded in PRODUCT_STOP_WORDS
                or folded in excluded
                or _technical_leak(surface)
                or _commercial_or_package_match(surface)
            ):
                continue
            grounded.setdefault(folded, surface)

    text_words: list[str] = []
    seen_text: set[str] = set()
    safe_glue = (
        "de", "da", "do", "para", "com", "em", "a", "o", "um", "uma", "até",
        "esse", "essa", "pro", "pra", "é", "são", "tem", "têm", "está", "estão",
        "fica", "ficam", "vem", "vêm", "destaque",
    )
    if "caneta" in _fold(product_name) and "apagavel" in _fold(product_name):
        safe_glue = (*safe_glue, "escrita", "escrever", "apagada", "apagado", "apagar", "apaga", "pode", "podem", "ser", "permite", "correção", "correções")
    for surface in (*grounded.values(), *safe_glue, *_GENERATION_REACTION_WORDS):
        folded = _fold(surface)
        if folded not in seen_text:
            seen_text.add(folded)
            text_words.append(surface)
    hashtags = [
        surface
        for surface in grounded.values()
        if hashtag_context_score(
            surface,
            product_name=product_name,
            product_context=context,
        ) > 0
    ]
    return tuple(text_words[:64]), tuple(hashtags[:32])


def _start_heart(main: str) -> str:
    text = re.sub(r"\s+", " ", main.replace("🧡", " ")).strip()
    return f"🧡 {text}" if text else "🧡"


def normalize_caption(
    caption: str,
    *,
    product_name: str = "",
    product_context: dict[str, Any] | None = None,
) -> CaptionNormalization:
    """Apply safe, auditable formatting and known adjective-inflection fixes."""
    raw = str(caption or "")
    corrections: list[str] = []
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if text != raw:
        corrections.append("line_endings_normalized")
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"(?<=[,;:])(?=\S)", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text).strip()
    if text != raw.strip():
        corrections.append("whitespace_and_punctuation_normalized")

    matches = list(HASHTAG_RE.finditer(text))
    hashtags = [match.group(1) for match in matches]
    main = HASHTAG_RE.sub("", text)
    main = re.sub(r"\s+", " ", main).strip()
    main, removed_trailing_punctuation = re.subn(r"[,.;:!?]+$", "", main)
    main = main.rstrip()
    if removed_trailing_punctuation:
        corrections.append("trailing_punctuation_removed")
    main, removed_caption_label = re.subn(
        r"^(\s*🧡\s*)?legenda curta\s*:\s*",
        lambda match: match.group(1) or "",
        main,
        count=1,
        flags=re.IGNORECASE,
    )
    if removed_caption_label:
        corrections.append("model_caption_label_removed")
        main = main.strip()
        main = re.sub(
            r"^(\s*🧡\s*)([a-zà-ÿ])",
            lambda match: match.group(1) + match.group(2).upper(),
            main,
            count=1,
            flags=re.IGNORECASE,
        )

    unique: list[str] = []
    seen: set[str] = set()
    for tag in hashtags:
        folded = _fold(tag)
        if folded in seen:
            corrections.append("duplicate_hashtag_removed")
            continue
        seen.add(folded)
        if hashtag_context_score(
            tag, product_name=product_name, product_context=product_context,
        ) <= 0:
            corrections.append("unrelated_hashtag_removed")
            continue
        unique.append(tag)
    if not unique:
        grounded_context = dict(product_context or {})
        if product_name and not grounded_context.get("productName"):
            grounded_context["productName"] = product_name
        _text_terms, grounded_hashtags = caption_generation_vocabulary(grounded_context)
        for tag in grounded_hashtags:
            if hashtag_context_score(
                tag,
                product_name=product_name,
                product_context=grounded_context,
            ) > 0:
                unique.append(tag)
                corrections.append("grounded_hashtag_inserted")
                break
    if len(unique) > 2:
        ranked = sorted(
            enumerate(unique),
            key=lambda entry: (
                -hashtag_context_score(
                    entry[1], product_name=product_name, product_context=product_context,
                ),
                entry[0],
            ),
        )
        keep_indices = {index for index, _tag in ranked[:2]}
        if len(unique) > 2:
            corrections.append("hashtags_limited_to_two_contextual_tags")
        unique = [tag for index, tag in enumerate(unique) if index in keep_indices]

    main_without_heart = main.replace("🧡", "")
    without_emoji = _remove_emojis(main_without_heart)
    if without_emoji != main_without_heart:
        corrections.append("excess_emojis_removed")
    without_emoji = re.sub(r"\s+", " ", without_emoji).strip()
    without_emoji, spelling_corrected = _normalize_context_spelling(
        without_emoji,
        product_name=product_name,
        product_context=product_context,
    )
    if spelling_corrected:
        corrections.append("vision_spelling_restored")
    without_emoji, case_corrected = _normalize_sentence_case(without_emoji)
    if case_corrected:
        corrections.append("sentence_case_normalized")
    without_emoji, agreement_corrected = _normalize_known_agreement(without_emoji)
    if agreement_corrected:
        corrections.append("known_adjective_agreement_inflected")
    heart_at_start = _start_heart(without_emoji)
    raw_heart_count = raw.count("🧡")
    marker = "ARMORED_ORANGE_HEART_MARKER"
    raw_main_with_marker = main.replace("🧡", marker)
    raw_main_keep_heart = _remove_emojis(raw_main_with_marker).replace(marker, "🧡")
    raw_main_keep_heart = re.sub(r"\s+", " ", raw_main_keep_heart).strip()
    if raw_heart_count == 0:
        corrections.append("orange_heart_inserted")
    elif raw_heart_count != 1 or heart_at_start != raw_main_keep_heart:
        corrections.append("orange_heart_moved_to_start")

    normalized = heart_at_start
    if unique:
        normalized += "\n" + " ".join("#" + tag for tag in unique)
    return CaptionNormalization(
        caption=normalized,
        corrections=tuple(dict.fromkeys(corrections)),
    )


def validate_caption(
    caption: str,
    *,
    product_name: str = "",
    product_context: dict[str, Any] | None = None,
) -> str:
    text = str(caption or "")
    if not text:
        raise CaptionPolicyError("legenda vazia")
    if re.search(r"[{}\[\]<>]", text):
        raise CaptionPolicyError("legenda contém marcador de preenchimento")
    if text.count("🧡") != 1:
        raise CaptionPolicyError("a legenda precisa ter exatamente um coração laranja")
    emoji_free = text.replace("🧡", "")
    if EMOJI_RE.search(emoji_free) or EMOJI_COMPONENT_RE.search(emoji_free):
        raise CaptionPolicyError("a legenda contém emoji além do coração laranja")
    if text != text.strip() or "\r" in text or re.search(r"[ \t]{2,}", text):
        raise CaptionPolicyError("formatação não normalizada")
    if re.search(r"\s+[,.;:!?]", text) or re.search(r"[,;:](?=\S)", text):
        raise CaptionPolicyError("pontuação não normalizada")
    if "\ufffd" in text or re.search(r"\?{2,}", text):
        raise CaptionPolicyError("resposta contém Unicode corrompido")

    hashtag_matches = list(HASHTAG_RE.finditer(text))
    raw_hashtags = [match.group(1) for match in hashtag_matches]
    if text.count("#") != len(hashtag_matches):
        raise CaptionPolicyError("hashtag malformada")
    if hashtag_matches:
        if text[hashtag_matches[-1].end():].strip():
            raise CaptionPolicyError("texto extra após as hashtags")
        for left, right in zip(hashtag_matches, hashtag_matches[1:]):
            if text[left.end():right.start()].strip():
                raise CaptionPolicyError("hashtags devem ficar juntas no final")

    hashtags = raw_hashtags
    if len({_fold(tag) for tag in hashtags}) != len(hashtags):
        raise CaptionPolicyError("hashtag duplicada")
    if not 1 <= len(hashtags) <= 2:
        raise CaptionPolicyError("a legenda precisa ter 1 ou 2 hashtags distintas")
    if any(len(tag) > 20 for tag in hashtags):
        raise CaptionPolicyError("hashtag longa demais")

    hard_error = _commercial_or_package_match(
        text,
        product_name=product_name,
        product_context=product_context,
    )
    if hard_error:
        raise CaptionPolicyError(hard_error)

    main_text = HASHTAG_RE.sub("", text)
    main = main_text.strip()
    if _has_vague_trailing_filler(main):
        raise CaptionPolicyError("texto principal termina em expressão vaga")
    if re.match(r"^🧡\s*(?:detalhe|caracter[ií]stica|descri[cç][aã]o)\s*:", main, re.IGNORECASE):
        raise CaptionPolicyError("legenda contém rótulo de catálogo em vez de comentário natural")
    words = WORD_RE.findall(main.replace("🧡", ""))
    neutral_rule = bool((product_context or {}).get("__title_rule_neutral_fallback"))
    if any(char.isdigit() for char in main):
        raise CaptionPolicyError("texto principal contém número ou especificação numérica")
    minimum_words = 1 if neutral_rule else 2
    if not minimum_words <= len(words) <= 5:
        raise CaptionPolicyError(
            f"texto principal contém {len(words)} palavras; o limite é de {minimum_words} a 5"
        )
    folded_words = [_fold(word) for word in words]
    repeatable_glue = {
        "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos",
        "e", "em", "na", "nas", "no", "nos", "o", "os", "para", "por",
        "pra", "pro", "um", "uma",
    }
    content_words = [word for word in folded_words if word not in repeatable_glue]
    if len(content_words) != len(set(content_words)):
        raise CaptionPolicyError("texto principal repete palavras")
    glue_words = {
        "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos",
        "e", "em", "na", "nas", "no", "nos", "para", "por", "pra", "pro",
        "um", "uma", "o", "os",
    }
    valid_glue_pairs = {
        ("para", "o"), ("para", "a"), ("para", "os"), ("para", "as"),
        ("de", "um"), ("de", "uma"), ("com", "o"), ("com", "a"),
        ("com", "os"), ("com", "as"), ("em", "um"), ("em", "uma"),
        ("e", "com"),
        ("sem", "o"), ("sem", "a"),
    }
    broken_glue_pair = any(
        left in glue_words and right in glue_words
        and not (words[index].casefold() == "é" and right == "de")
        and (left, right) not in valid_glue_pairs
        for index, (left, right) in enumerate(zip(folded_words, folded_words[1:]))
    )
    if (
        broken_glue_pair
            or folded_words[-1] in {"com", "da", "das", "de", "do", "dos", "e", "em", "na", "nas", "no", "nos", "para", "por", "pra", "pro"}
    ):
        raise CaptionPolicyError("texto principal contém ligação gramatical quebrada")
    if folded_words.count("em") > 1:
        raise CaptionPolicyError("texto principal repete a preposição em")
    if _has_single_character_product_head_typo(
        words,
        product_name=product_name,
        product_context=product_context,
    ):
        raise CaptionPolicyError("texto principal contém possível erro de digitação no nome do produto")
    if _has_known_agreement_error(words):
        raise CaptionPolicyError("texto principal contém erro de concordância de artigo ou adjetivo")
    if _is_incomplete_article_label(words):
        raise CaptionPolicyError("texto principal é um rótulo incompleto sem predicado")
    hashtags_have_anchor = _hashtags_have_product_anchor(
        hashtags, product_name=product_name, product_context=product_context,
        words=words,
    )
    if _has_unlinked_product_nouns(words):
        raise CaptionPolicyError("texto principal combina substantivos de produto sem ligação natural")
    if not _secondary_product_noun_is_comparative(
        words, product_name=product_name, product_context=product_context,
    ):
        raise CaptionPolicyError(
            "substantivo secundário do título sem ligação natural; use comparação explícita"
        )
    if _has_unnatural_bag_device_relation(words):
        raise CaptionPolicyError(
            "relação pouco natural: bolsa para computador descreve finalidade; não use bolsa de computador"
        )
    if _caption_repeats_title_category_fragment(
        words,
        product_name=product_name,
        product_context=product_context,
    ):
        raise CaptionPolicyError(
            "legenda copia expressão distintiva do produto em fragmento de título"
        )
    if _caption_is_title_keyword_list(
        words,
        product_name=product_name,
        product_context=product_context,
    ):
        raise CaptionPolicyError(
            "legenda permanece como fragmento de título em sequência de palavras-chave"
        )

    # Check copied title phrases only against the main sentence. Separate
    # contextual hashtags can appear next to one another and must not be
    # accidentally recombined into a product-title phrase.
    main_only = HASHTAG_RE.sub("", text)
    folded_caption = _fold(_remove_emojis(main_only))
    normalized_caption_tokens = [
        token for token in WORD_RE.findall(folded_caption)
        if token.casefold() not in PRODUCT_STOP_WORDS
    ]
    normalized_caption = " ".join(normalized_caption_tokens)

    if not _has_title_rule_evidence(words, product_context):
        for phrase in _product_phrases(product_name):
            if re.search(rf"\b{re.escape(phrase)}\b", normalized_caption):
                raise CaptionPolicyError("legenda copia expressão distintiva do produto")

    if _caption_mentions_product_category(
        words,
        product_name=product_name,
        product_context=product_context,
    ) and not _category_has_confirmed_caption_detail(
        words,
        product_name=product_name,
        product_context=product_context,
    ):
        raise CaptionPolicyError(
            "nome do produto sem um detalhe confirmado da Vision"
        )

    hashtag_tokens = {_fold(tag) for tag in hashtags}
    trusted_title_rule = _has_title_rule_evidence(words, product_context)
    if not (neutral_rule or trusted_title_rule) and hashtag_tokens & _hashtag_sequences(product_name):
        raise CaptionPolicyError("hashtag recompõe explicitamente o produto")

    brand_check_tokens = (
        set(normalized_caption_tokens)
        if neutral_rule
        else set(re.findall(r"[a-z0-9]+", folded_caption))
    )
    if _brand_model_tokens(product_context) & brand_check_tokens:
        raise CaptionPolicyError("legenda revela marca ou modelo do contexto V1")

    if _technical_leak(text):
        raise CaptionPolicyError("legenda revela medida ou especificação técnica")

    if _caption_uses_unconfirmed_spatial_relation(
        words,
        product_name=product_name,
        product_context=product_context,
    ):
        raise CaptionPolicyError(
            "relação espacial não confirmada pela Vision"
        )

    if not _main_phrase_is_contextual(
        words,
        product_name=product_name,
        product_context=product_context,
    ):
        raise CaptionPolicyError("texto principal contém termo sem suporte no contexto Vision")

    if not main.startswith("🧡 "):
        raise CaptionPolicyError("coração laranja deve estar no início da legenda")

    if caption_product_anchor_terms(
        product_context, product_name=product_name,
    ) and not hashtags_have_anchor and not _has_title_rule_evidence(
        words, product_context,
    ):
        raise CaptionPolicyError(
            "as hashtags precisam identificar a categoria ou substantivo principal"
        )

    for tag in hashtags:
        if hashtag_context_score(
            tag, product_name=product_name, product_context=product_context,
        ) <= 0 and not (
            _has_title_rule_evidence(words, product_context)
            and _fold(tag) == _fold(str((product_context or {}).get("__title_rule_hashtag") or ""))
        ):
            raise CaptionPolicyError("hashtag sem relação confiável com o produto")

    # Description/category overlap is deliberately allowed. With only 2–3
    # words available, rejecting ordinary contextual vocabulary causes false
    # negatives and unnecessary Gemini calls.
    if not hashtag_matches or text != f"{main}\n{' '.join('#' + tag for tag in hashtags)}":
        raise CaptionPolicyError("legenda não está na forma canonical da Policy")
    return text
