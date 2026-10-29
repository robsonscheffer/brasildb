# Protótipo privado: rua → publicação → apuração → comemoração

Objetivo: avaliar a escala dos planos abertos e o ritmo da direção editorial já escolhida, não oferecer novas direções.

Preview implementado em branch isolada. Para abrir, forneça a pasta local das cópias privadas:

```sh
python3 scripts/preview_espera.py --media-root "$ESPERA_MEDIA_ROOT"
```

Endereço: `http://127.0.0.1:52018/espera-prototype/`. A pasta deve conter `curadoria-primeira/niteroi-felipe-publicada.jpg`, `curadoria-primeira/bh-publicada.jpg` e `curadoria-segunda/pt-reel-poster.jpg`. O servidor recusa iniciar sem esses arquivos e não serve diretórios nem outras fontes privadas. Não usar um servidor estático genérico: o HTML é um template renderizado pelo preview.

A decisão de composição ainda depende da leitura do protótipo. Não publicar nem promover esta branch a main sem resolver direitos e revisão editorial.

1. Criar `docs/site/espera-prototype/` com `index.html`, `style.css`, `script.js` e `content.json`. Conteúdo documental separado, fotos completas, fontes próximas e parciais sem interpolação.
2. Criar `scripts/preview_espera.py`: servidor apenas em loopback, sem dependências; recebe o diretório das cópias privadas via argumento. Não copia nem publica mídia; não serve outros arquivos do repositório.
3. Conferir no navegador em desktop e celular, com movimento reduzido e JavaScript desligado. Verificar imagens, links internos, ausência de overflow e números contra as capturas consultadas.

Limites: preservar a página existente; sem deploy, contatos, áudio não conferido ou commit de mídia. O post não tem minuto confirmado. Imagens não têm autorização de publicação. Resultado nacional e parciais jornalísticas são coberturas distintas. A sequência começa na noite, volta explicitamente ao dia e termina na comemoração, sem sincronizar fotos com parciais.
