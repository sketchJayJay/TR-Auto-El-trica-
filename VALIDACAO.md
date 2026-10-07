# Validação da entrega — 07/10/2026

- 12 testes de integração concluídos com sucesso em uma cópia temporária da base.
- Os registros de clientes, veículos, peças, OS e itens foram comparados linha por linha com o arquivo enviado. O banco em `seed/oficina.db` permanece idêntico ao original, inclusive SHA-256.
- Login, sessão, CSRF, limite de tentativas, entradas inválidas e dados com acentos foram conferidos.
- Criação, edição, mudança de situação e exclusão de OS; cálculos com desconto e arredondamento HALF_UP; clientes, veículos, histórico e estoque foram testados.
- Relatórios diários/mensais respeitam o total das OS, descontos e cancelamentos.
- Backup do banco com WAL, validação de imagem e preservação dos dados ao reinicializar foram testados.
- Chromium: 45 combinações de página e largura, em 1440, 1366, 768, 390 e 320 pixels. Sem transbordamento horizontal da página, erros de JavaScript ou recursos com falha.
- No navegador: seleção de cliente, peças cadastradas e itens avulsos, totais ao vivo, criação, edição, situação, confirmação/cancelamento da exclusão, navegação mobile e tema escuro.
- Uma OS real foi impressa em PDF A4 de uma página e conferida visualmente. As prévias estão na pasta `PREVIAS`.
- Gunicorn foi iniciado e usado para os testes HTTP e de navegador. Os arquivos Dockerfile e Compose e suas configurações de volume estão incluídos.

## Limites da conferência

O deploy no seu Coolify não foi executado, pois o servidor e o domínio não foram fornecidos. Não foi possível construir a imagem Docker neste ambiente. HTTPS, permissões do volume, instalação do atalho e impressão física devem ser conferidos no seu servidor e nos seus dispositivos após o deploy. O sistema exige conexão com a internet e não sincroniza lançamentos offline.

## Executar os testes novamente

Com Python 3.12 e as dependências de `requirements.txt` instaladas:

```bash
python -m unittest discover -s tests -v
```

Os testes usam pastas temporárias e não modificam `seed/oficina.db` nem a base de produção.
