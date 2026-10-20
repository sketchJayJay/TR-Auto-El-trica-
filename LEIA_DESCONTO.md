# TR Auto — desconto em reais ou porcentagem

## Como atualizar
1. Extraia o ZIP.
2. Envie app.py e as pastas static, templates e tests para a raiz do mesmo repositório no GitHub, substituindo os arquivos correspondentes. Não envie apenas o ZIP nem crie uma pasta externa no repositório.
3. Confirme o Commit changes na branch main.
4. Faça Redeploy no Coolify. Mantenha as variáveis atuais e o volume /data.

A atualização adiciona uma coluna à base existente automaticamente, sem apagar as OS. O pacote não contém banco de dados. As OS antigas continuam com desconto em porcentagem.

## Uso
Em Nova OS ou Editar OS, vá a Valores e pagamento. Escolha Tipo de desconto: Porcentagem (%) ou Valor em reais (R$). Digite o desconto no campo correspondente. O resumo e a OS impressa mostram o desconto e o total final.
Exemplo: mão de obra R$ 200, desconto em reais R$ 20, total R$ 180.
As opções são alternativas: apenas a selecionada é aplicada. O desconto em reais permanece fixo ao editar o valor do serviço e não pode superar o total bruto.

## Validação
Base: sketchJayJay/TR-Auto-El-trica-, commit 0ad90549ac7e605a790a747d9335d16379832c37, consultado em 20/10/2026.
15 testes de integração aprovados, incluindo migração preservando dados, descontos antigos, valor fixo, centavos, limites, edição e impressão.
Teste em navegador nas larguras 1440, 390 e 320: alternância de modos, resumo instantâneo, limite de desconto, salvar, reabrir para edição e imprimir. Sem erros JavaScript nem rolagem horizontal.
