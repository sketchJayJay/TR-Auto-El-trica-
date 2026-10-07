# TR Auto — Oficina Online Premium

Versão refeita para notebook e celular, preparada para publicar no seu Coolify.
O pacote inclui a base enviada: **317 OS, 195 clientes, 311 veículos, 174 peças e 906 itens de OS**.

## Publicar no Coolify (Dockerfile — recomendado)

1. Extraia o ZIP. Envie o conteúdo de `TR_AUTO_ONLINE_PREMIUM` para a raiz de um **repositório privado**. O banco em `seed/oficina.db` contém os seus dados de atendimento.
2. No Coolify, crie uma aplicação a partir desse repositório. Selecione **Dockerfile** como build pack. Base Directory: `/`. Dockerfile Location: `/Dockerfile`.
3. Configure as variáveis abaixo em **Environment Variables**, disponíveis em runtime. Se o painel oferecer a opção de segredo, ative para senha e chave.

| Variável | Valor |
|---|---|
| `ADMIN_USERNAME` | Seu usuário de acesso, por exemplo `admin` |
| `ADMIN_PASSWORD` | Uma senha sua, com no mínimo 10 caracteres |
| `SECRET_KEY` | Uma chave aleatória de pelo menos 32 caracteres |
| `DATA_DIR` | `/data` |
| `TZ` | `America/Sao_Paulo` |
| `COOKIE_SECURE` | `true` |
| `TRUST_PROXY` | `true` (Coolify com proxy na frente da aplicação) |

Para gerar a chave no terminal, execute:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

4. Configure **Ports Exposes: `8000`**. A aplicação escuta nessa porta. Não precisa expor a porta diretamente na internet.
5. Em **Persistent Storage**, crie um volume com nome `tr-auto-data` e **Destination Path `/data`**. Mantenha esse mesmo volume nas atualizações. Faça essa configuração **antes do primeiro deploy**.
6. Configure o seu endereço com **HTTPS**. No campo de domínio, use `https://seu-dominio.com` (o proxy deve direcionar para a porta interna 8000; informe a porta no domínio se a sua versão do Coolify solicitar).
7. Faça o deploy. Se estiver configurando um health check pelo painel: método GET, caminho `/health`, porta `8000`, código esperado `200`. O Dockerfile também contém um health check.
8. Acesse o endereço e entre com o usuário e a senha que você configurou.
9. Confira os registros e baixe o primeiro backup em **Configurações → Baixar backup**.

Não há senha padrão. Se faltar senha ou chave, o servidor exibirá nos logs a variável que precisa ser configurada.

## Persistência e futuras atualizações

- O sistema grava o banco e as imagens em `/data`.
- `seed/oficina.db` é copiado **apenas se ainda não existe `/data/oficina.db`**. Atualizações não substituem um banco já existente.
- Depois do primeiro deploy, o banco do volume é a base ativa. Use sempre o mesmo recurso e volume para manter os dados.
- Um volume é armazenamento persistente; ele não substitui uma cópia de segurança. Baixe backups regularmente e configure também o backup do volume no Coolify quando disponível.
- Não exclua o volume nem use `docker compose down -v` em produção. Um novo servidor ou um novo volume precisa receber uma cópia do banco ativo.

## Alternativa: Docker Compose

O arquivo `docker-compose.yml` já declara o volume `tr_auto_data:/data`. Use-o ao criar uma aplicação Docker Compose com o repositório. Configure as mesmas variáveis e o domínio HTTPS da aplicação `tr-auto` na porta 8000. Para esse tipo de recurso, os mounts são definidos no Compose; revise os volumes detectados pelo Coolify antes de publicar.

Para testar localmente com Docker, copie `.env.example` para `.env`, preencha senha e chave, use `COOKIE_SECURE=false` e publique a porta apenas na máquina local com este override:

```yaml
# compose.local.yml
services:
  tr-auto:
    ports:
      - "127.0.0.1:8000:8000"
```

```bash
docker compose -f docker-compose.yml -f compose.local.yml up --build -d
```

Abra `http://localhost:8000`. Em produção por HTTPS, mantenha `COOKIE_SECURE=true`.

## Uso no celular

O endereço online é o mesmo no celular e no notebook. No celular há navegação inferior, menu com as demais opções e cartões que adaptam as listas ao toque.

No iPhone: Safari → Compartilhar → Adicionar à Tela de Início. No Android: menu do navegador → Adicionar à tela inicial. O atalho possui ícone próprio e abre com aparência de aplicativo quando suportado. É necessária conexão com a internet; não há armazenamento offline de OS.

## O que mudou

- Painel com valor em OS no mês, serviços em aberto, clientes, peças com até 3 unidades, movimento de 7 dias e fluxo de atendimento.
- Tema claro e escuro, marca TR Auto, navegação lateral no notebook e inferior no celular.
- Busca de OS por cliente, placa ou número; filtro por situação; mudança de situação na lista e no detalhe.
- Cadastro e edição de OS com seleção de cliente e veículo, peças do cadastro, itens avulsos, subtotal ao vivo, mão de obra, desconto e pagamento.
- Clientes com veículos e histórico; estoque com busca, edição e exclusão; relatórios diários e mensais.
- OS pronta para impressão A4 / salvar PDF, logo, Pix, condições e campo de assinatura.
- WhatsApp abre uma mensagem para o cliente. Para enviar o documento, salve a OS em PDF e anexe no WhatsApp.
- Imagens editáveis e download de backup consistente do SQLite, incluindo imagens.
- Login por usuário e senha, limitação de tentativas, sessão protegida e validação dos formulários.

## Regras conservadas / esclarecimentos

Os totais representam **valores de OS**, por data de criação, descontando descontos e excluindo canceladas. O sistema original não controla baixas de recebimento nem despesas; portanto esses indicadores não representam caixa recebido ou lucro.

As peças selecionadas na OS conservam descrição e preço do atendimento. A quantidade em estoque é ajustada manualmente na tela Estoque, seguindo o comportamento da base enviada. Não há baixa automática de peças nem reversão de estoque por status.

A edição do cadastro de um cliente ou veículo reflete os dados atuais nas OS vinculadas, como no sistema anterior. Os preços dos itens antigos permanecem próprios da OS.

## Restaurar um backup

1. Baixe o backup atual antes de substituir arquivos.
2. Pare a aplicação no Coolify. Extraia o ZIP de backup em uma pasta temporária.
3. Copie `oficina.db`, `logo.png` e `qr_pix.png` do backup para a pasta correspondente ao volume `/data` no servidor. Com a aplicação parada, remova os arquivos antigos `oficina.db-wal` e `oficina.db-shm`, se existirem, antes de colocar o banco restaurado. Não restaure com processos conectados ao banco.
4. Mantenha as permissões de leitura e escrita do volume e reinicie a aplicação. Confira registros e imagens.

## Validação

Os testes no pacote usam cópias temporárias da base e verificam login, proteção de formulários, criação/edição/exclusão de OS, descontos, filtros, clientes, estoque, backup e preservação dos dados após reiniciar. O arquivo `VALIDACAO.md` registra os resultados e limites da conferência.

Documentação de referência: [Coolify — armazenamento persistente](https://coolify.io/docs/applications/configuration/persistent-storage) e [volumes](https://coolify.io/docs/core/persistent-storage/storage-mounts/volume-mounts).
