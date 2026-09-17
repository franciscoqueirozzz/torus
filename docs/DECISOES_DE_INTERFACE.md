# Escrita e comportamento da interface

Revisão: 30/08/2026. A aplicação não usa LLM para redigir mensagens, classificar falas ou recomendar ações. Os textos da interface são definidos no código; as recomendações seguem regras explícitas.

## Critérios adotados

- A paleta mantém a identidade anterior do Torus: grafite e cinza nas superfícies, laranja nas ações principais e verde nos detalhes e confirmações. Os botões laranja usam texto escuro para facilitar a leitura.
- A tela de entrada e a marca lateral retomam a composição original, a pedido do responsável pelo projeto: símbolo T, nome TORUS, título à esquerda e cartões de acesso por perfil. Clientes, tarefas e os demais fluxos da versão atual foram preservados; os cartões apenas preenchem as credenciais de demonstração.
- Botões nomeiam o resultado: “Cadastrar cliente”, “Criar tarefa”, “Salvar nova senha”.
- Mensagens de erro explicam o que conferir. O formulário conserva os dados para correção.
- Texto obrigatório permanece visível em rótulos; exemplos aparecem como apoio.
- A interface distingue clientes, reuniões e tarefas. A contagem de clientes não usa o número de transcrições como substituto.
- Risco e expansão aparecem em pontos de 0 a 100. Confiança do classificador e chance real de um resultado não são tratadas como equivalentes.
- A tela não chama uma conta de “saudável” por ter recebido um escore baixo.
- A desativação informa que sessões serão encerradas e histórico será preservado.

## Exemplos aplicados

| Antes | Nesta versão | Motivo |
|---|---|---|
| Renovações em risco | Clientes para revisar | O sistema não comprova data de renovação ou cancelamento |
| Saudável | Baixo sinal de risco | Um sinal baixo não garante a situação da conta |
| 72% de risco | 72 pts | O índice não foi calibrado como probabilidade |
| Gerar análise da conta | Analisar e salvar reunião | Informa a unidade analisada e que o histórico será atualizado |
| Failed to fetch | Não foi possível conectar ao Torus; confira o inicializador | Explica o problema de conexão sem afirmar uma causa não verificada |

## Referências consultadas

O [GOV.UK Design System: mensagens de erro](https://design-system.service.gov.uk/components/error-message/) orienta a explicar o problema e a correção, preservando as respostas do formulário. O [componente de botões](https://design-system.service.gov.uk/components/button/) serviu de referência para ações explícitas e hierarquia entre ações principais e secundárias. As frases em português foram escritas para os fluxos do Torus; não são traduções de um modelo de marketing.

A [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) fundamentou a confirmação da senha em ações administrativas, a exigência de senha atual na alteração e o encerramento de sessões. Novas senhas usam de 15 a 128 caracteres, sem regras artificiais de mistura de tipos de caracteres. As senhas antigas de demonstração continuam funcionando por compatibilidade local.

Não foi implementada certificação de acessibilidade ou segurança. Persistem limites descritos no manual: dados sintéticos, ausência de MFA, recuperação de senha por e-mail, bloqueio de senhas vazadas e controle de tentativas de login.
