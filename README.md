# Torus Meeting Intelligence

O Torus recebe a transcrição de uma reunião em JSON e classifica cada fala como risco de cancelamento, objeção de preço, oportunidade de expansão, satisfação ou conversa neutra. Em seguida, consolida risco, oportunidade, sentimento, produtos TOTVS citados e a ação comercial recomendada para a conta.

O acesso é separado por perfil: vendedores consultam somente as próprias reuniões, enquanto gerentes visualizam a equipe inteira e podem atribuir novas análises a um vendedor.

Na versão 1.1, o acompanhamento inclui clientes cadastrados, histórico por cliente, tarefas com prazo e prioridade, gestão de acessos e relatórios. A classificação continua local, sem LLM.

## Recursos principais

- login com sessão temporária e senhas protegidas por PBKDF2;
- painéis distintos para vendedores e gerentes;
- envio de reunião por formulário ou arquivo JSON;
- classificação de intenção em cinco categorias comerciais;
- indicadores de churn, oportunidade, sentimento e participação na conversa;
- histórico persistido em SQLite;
- quatro tabelas organizacionais exigidas e a `tb_tarefa`, sincronizadas com o banco operacional;
- cadastro e edição de clientes, com etapa do atendimento e anotações;
- tarefas pendentes, em atraso ou concluídas, vinculadas ao cliente e à reunião;
- cadastro e desativação de usuários pelo gerente, com confirmação de senha;
- troca de senha, que encerra todas as sessões da conta;
- detalhamento dos pontos nas novas análises e comparação dos registros do cliente;
- exportação CSV e relatório por reunião para imprimir ou salvar em PDF;
- validação automatizada da API, das permissões e do pipeline analítico.

O projeto não envia transcrições para serviços externos e não depende de LLM. O classificador executado localmente é uma Regressão Logística, com pesos em `backend/models/intent_classifier.json`. A entrada já deve estar transcrita; não há captura ou transcrição de áudio.

## Organização

```text
Torusproject/
├── frontend/                   # HTML, CSS e JavaScript da interface
├── README.md                   # visão geral e execução
├── docs/                       # documentação do produto em Markdown e PDF
├── scripts/                    # iniciar e encerrar o servidor
└── backend/
    ├── app/                    # API, autenticação e análise
    ├── examples/               # reunião de exemplo
    ├── models/                 # modelo de execução e metadados
    ├── runtime/                # banco local, ignorado pelo Git
    ├── tests/                  # testes automatizados
    └── pyproject.toml          # dependências e ferramentas
```

## Como abrir no Windows

Com uv disponível no PATH e Python 3.10 ou superior, dê dois cliques em `INICIAR_TORUS.cmd`. O inicializador mantém a API ativa em segundo plano e abre `http://127.0.0.1:8000` no navegador. Para encerrar, use `ENCERRAR_TORUS.cmd`. Fechar a página não encerra o servidor.

Na primeira execução, o uv pode levar alguns segundos para preparar as dependências.

## Execução pelo terminal

No PowerShell, a partir da pasta do projeto:

```powershell
cd backend
uv sync --extra dev
uv run python -m uvicorn app.api:app --reload --port 8000
```

Abra `http://127.0.0.1:8000`. A documentação interativa da API fica em `http://127.0.0.1:8000/docs`.

### Acessos de demonstração

| Perfil | E-mail | Senha |
|---|---|---|
| Gerente | `manager@torus.ai` | `Torus@2026` |
| Vendedora | `ana@torus.ai` | `Vendas@2026` |
| Vendedor | `carlos@torus.ai` | `Vendas@2026` |

Essas contas têm senhas públicas e existem somente para demonstração local. A configuração atual não deve ser exposta à internet. Reiniciar não apaga o histórico nem redefine senhas de usuários já existentes.

## Documentação

- [Documentação completa](docs/DOCUMENTACAO_TORUS.md): instalação, uso dos perfis, arquitetura, entrada, API, modelo, indicadores, segurança e manutenção.
- [Versão em PDF](docs/DOCUMENTACAO_TORUS.pdf): mesmo conteúdo para leitura e compartilhamento.
- Exemplo de transcrição: `backend/examples/sample_meeting.json`.
- [Decisões de interface e escrita](docs/DECISOES_DE_INTERFACE.md): critérios, exemplos e fontes consultadas.
- [Esquema do banco](docs/ESQUEMA_BANCO.md): tabelas exigidas, relacionamentos e correspondência com a aplicação.

O banco fica em `backend/runtime/torus.db`, fora do versionamento. Não apague esse arquivo para atualizar a aplicação.

Clientes são vinculados às reuniões antigas automaticamente na inicialização. A migração é repetível e não remove reuniões. Antes de atualizar um banco existente, faça uma cópia de segurança. O responsável é definido no cadastro do cliente e não pode ser transferido pela interface atual.

Para usar: cadastre o cliente em **Clientes**, selecione-o em **Analisar reunião** e envie a transcrição. Abra a análise e use **Criar tarefa de acompanhamento** para registrar o próximo contato. Não há envio automático de mensagens ou e-mails.

## Verificação

Para executar os 28 testes e a verificação do código, dentro de `backend`:

```powershell
uv run --extra dev python -m unittest discover -s tests -v
uv run --extra dev ruff check .
```

## Limites atuais

O modelo foi avaliado em 25 frases sintéticas, com 48% de acurácia. Os indicadores combinam previsões com regras fixas e não representam probabilidades calibradas de cancelamento ou venda. Confira as falas antes de tomar uma decisão sobre o cliente.
