# Esquema organizacional do banco

O Torus mantém suas tabelas operacionais para não quebrar login, clientes, tarefas e análises. Como complemento, o banco contém as quatro tabelas exigidas no modelo de dados e a `tb_tarefa`, acrescentada para organizar o acompanhamento comercial. Elas são preenchidas inicialmente com o histórico existente e atualizadas por gatilhos do SQLite quando a aplicação grava ou altera registros.

```mermaid
erDiagram
    tb_cliente ||--o{ tb_reuniao : participa
    tb_vendedor ||--o{ tb_reuniao : realiza
    tb_reuniao ||--|| tb_transcricoes : possui
    tb_cliente ||--o{ tb_tarefa : demanda
    tb_vendedor ||--o{ tb_tarefa : acompanha
    tb_reuniao o|--o{ tb_tarefa : origina

    tb_cliente {
        TEXT id_cliente PK
        TEXT nome_cliente
        TEXT tipo_empresa_cliente
        TEXT data_cadastro_cliente
        TEXT telefone_cliente
    }
    tb_vendedor {
        TEXT id_vendedor PK
        TEXT nome_vendedor
        TEXT email_vendedor
        TEXT equipe_vendedor
    }
    tb_reuniao {
        TEXT id_reuniao PK
        TEXT titulo_reuniao
        TEXT data_reuniao
        TEXT horario_reuniao
        INTEGER duracao_reuniao
        TEXT plataforma_reuniao
        TEXT estagio_negociacao
        TEXT status_negociacao
        TEXT tb_cliente_id_cliente FK
        TEXT tb_vendedor_id_vendedor FK
    }
    tb_transcricoes {
        TEXT id_transcricoes PK
        TEXT texto_completo
        TEXT palavras_chave
        REAL sentimento_geral
        TEXT data_transcricao
        TEXT tb_reuniao_id_reuniao FK
    }
    tb_tarefa {
        TEXT id_tarefa PK
        TEXT titulo_tarefa
        TEXT descricao_tarefa
        TEXT data_prazo
        TEXT prioridade_tarefa
        TEXT status_tarefa
        TEXT data_criacao
        TEXT data_conclusao
        TEXT tb_cliente_id_cliente FK
        TEXT tb_vendedor_id_vendedor FK
        TEXT tb_reuniao_id_reuniao FK
    }
```

## Correspondência com a aplicação

| Tabela exigida | Origem operacional | Observação |
|---|---|---|
| `tb_cliente` | `customers` | Segmento preenche o tipo de empresa; telefone fica disponível para cadastro futuro |
| `tb_vendedor` | `users` | Somente usuários com perfil de vendedor; a equipe padrão é Comercial |
| `tb_reuniao` | `meetings` | Data e horário vêm do registro; duração ainda não é coletada e começa em zero |
| `tb_transcricoes` | `meetings` | Reúne o texto das falas, termos encontrados e sentimento normalizado de 0 a 1 |
| `tb_tarefa` | `tasks` | Organiza prazos, prioridades e situação; a reunião de origem é opcional e o vendedor vem da carteira do cliente |

Os tipos `VARCHAR2`, `DATE` e `NUMBER` do diagrama de referência são tipos do Oracle. No SQLite, foram usados `TEXT`, `INTEGER` e `REAL`, preservando os mesmos campos e relacionamentos. As chaves da camada organizacional são textuais, seguindo o padrão do modelo fornecido.

As tabelas operacionais continuam sendo a fonte usada pela API. Essa separação evita uma migração destrutiva e mantém todos os recursos já implementados. Prioridades e situações são apresentadas na camada organizacional como `Normal`, `Alta`, `Pendente` e `Concluída`.
