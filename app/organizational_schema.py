"""Tabelas exigidas pelo modelo de dados, sincronizadas com o banco operacional."""

from __future__ import annotations

import sqlite3


def migrate(connection: sqlite3.Connection) -> None:
    """Cria e atualiza a camada organizacional sem substituir as tabelas da API."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tb_cliente (
            id_cliente TEXT PRIMARY KEY,
            nome_cliente TEXT NOT NULL,
            tipo_empresa_cliente TEXT NOT NULL DEFAULT '',
            data_cadastro_cliente TEXT NOT NULL DEFAULT CURRENT_DATE,
            telefone_cliente TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS tb_vendedor (
            id_vendedor TEXT PRIMARY KEY,
            nome_vendedor TEXT NOT NULL,
            email_vendedor TEXT NOT NULL UNIQUE COLLATE NOCASE,
            equipe_vendedor TEXT NOT NULL DEFAULT 'Comercial'
        );

        CREATE TABLE IF NOT EXISTS tb_reuniao (
            id_reuniao TEXT PRIMARY KEY,
            titulo_reuniao TEXT NOT NULL,
            data_reuniao TEXT NOT NULL,
            horario_reuniao TEXT NOT NULL,
            duracao_reuniao INTEGER NOT NULL DEFAULT 0,
            plataforma_reuniao TEXT NOT NULL DEFAULT 'Torus',
            estagio_negociacao TEXT NOT NULL DEFAULT '',
            status_negociacao TEXT NOT NULL DEFAULT 'Analisada',
            tb_cliente_id_cliente TEXT NOT NULL,
            tb_vendedor_id_vendedor TEXT NOT NULL,
            FOREIGN KEY (tb_cliente_id_cliente)
                REFERENCES tb_cliente(id_cliente) ON UPDATE CASCADE,
            FOREIGN KEY (tb_vendedor_id_vendedor)
                REFERENCES tb_vendedor(id_vendedor) ON UPDATE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tb_transcricoes (
            id_transcricoes TEXT PRIMARY KEY,
            texto_completo TEXT NOT NULL,
            palavras_chave TEXT NOT NULL DEFAULT '',
            sentimento_geral REAL NOT NULL DEFAULT 0,
            data_transcricao TEXT NOT NULL,
            tb_reuniao_id_reuniao TEXT NOT NULL UNIQUE,
            FOREIGN KEY (tb_reuniao_id_reuniao)
                REFERENCES tb_reuniao(id_reuniao) ON UPDATE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tb_tarefa (
            id_tarefa TEXT PRIMARY KEY,
            titulo_tarefa TEXT NOT NULL,
            descricao_tarefa TEXT NOT NULL DEFAULT '',
            data_prazo TEXT NOT NULL,
            prioridade_tarefa TEXT NOT NULL DEFAULT 'Normal',
            status_tarefa TEXT NOT NULL DEFAULT 'Pendente',
            data_criacao TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            data_conclusao TEXT,
            tb_cliente_id_cliente TEXT NOT NULL,
            tb_vendedor_id_vendedor TEXT NOT NULL,
            tb_reuniao_id_reuniao TEXT,
            FOREIGN KEY (tb_cliente_id_cliente)
                REFERENCES tb_cliente(id_cliente) ON UPDATE CASCADE,
            FOREIGN KEY (tb_vendedor_id_vendedor)
                REFERENCES tb_vendedor(id_vendedor) ON UPDATE CASCADE,
            FOREIGN KEY (tb_reuniao_id_reuniao)
                REFERENCES tb_reuniao(id_reuniao) ON UPDATE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_tb_reuniao_cliente
            ON tb_reuniao(tb_cliente_id_cliente);
        CREATE INDEX IF NOT EXISTS idx_tb_reuniao_vendedor
            ON tb_reuniao(tb_vendedor_id_vendedor);
        CREATE INDEX IF NOT EXISTS idx_tb_transcricoes_reuniao
            ON tb_transcricoes(tb_reuniao_id_reuniao);
        CREATE INDEX IF NOT EXISTS idx_tb_tarefa_cliente_prazo
            ON tb_tarefa(tb_cliente_id_cliente, data_prazo);
        CREATE INDEX IF NOT EXISTS idx_tb_tarefa_vendedor_status
            ON tb_tarefa(tb_vendedor_id_vendedor, status_tarefa);
        CREATE INDEX IF NOT EXISTS idx_tb_tarefa_reuniao
            ON tb_tarefa(tb_reuniao_id_reuniao);

        CREATE TRIGGER IF NOT EXISTS trg_torus_users_organizacao_insert
        AFTER INSERT ON users WHEN NEW.role = 'seller'
        BEGIN
            INSERT INTO tb_vendedor (
                id_vendedor, nome_vendedor, email_vendedor, equipe_vendedor
            ) VALUES (CAST(NEW.id AS TEXT), NEW.name, NEW.email, 'Comercial')
            ON CONFLICT(id_vendedor) DO UPDATE SET
                nome_vendedor = excluded.nome_vendedor,
                email_vendedor = excluded.email_vendedor;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_torus_users_organizacao_update
        AFTER UPDATE OF name, email, role ON users WHEN NEW.role = 'seller'
        BEGIN
            INSERT INTO tb_vendedor (
                id_vendedor, nome_vendedor, email_vendedor, equipe_vendedor
            ) VALUES (CAST(NEW.id AS TEXT), NEW.name, NEW.email, 'Comercial')
            ON CONFLICT(id_vendedor) DO UPDATE SET
                nome_vendedor = excluded.nome_vendedor,
                email_vendedor = excluded.email_vendedor;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_torus_customers_organizacao_insert
        AFTER INSERT ON customers
        BEGIN
            INSERT INTO tb_cliente (
                id_cliente, nome_cliente, tipo_empresa_cliente,
                data_cadastro_cliente, telefone_cliente
            ) VALUES (
                CAST(NEW.id AS TEXT), NEW.name, NEW.segment,
                date(NEW.created_at), ''
            ) ON CONFLICT(id_cliente) DO UPDATE SET
                nome_cliente = excluded.nome_cliente,
                tipo_empresa_cliente = excluded.tipo_empresa_cliente;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_torus_customers_organizacao_update
        AFTER UPDATE OF name, segment ON customers
        BEGIN
            UPDATE tb_cliente SET
                nome_cliente = NEW.name,
                tipo_empresa_cliente = NEW.segment
            WHERE id_cliente = CAST(NEW.id AS TEXT);
        END;

        CREATE TRIGGER IF NOT EXISTS trg_torus_meetings_organizacao_insert
        AFTER INSERT ON meetings
        BEGIN
            INSERT INTO tb_reuniao (
                id_reuniao, titulo_reuniao, data_reuniao, horario_reuniao,
                duracao_reuniao, plataforma_reuniao, estagio_negociacao,
                status_negociacao, tb_cliente_id_cliente,
                tb_vendedor_id_vendedor
            ) VALUES (
                CAST(NEW.id AS TEXT), NEW.title, date(NEW.created_at),
                time(NEW.created_at), 0, 'Torus',
                COALESCE((SELECT stage FROM customers WHERE id=NEW.customer_id), ''),
                'Analisada', CAST(NEW.customer_id AS TEXT),
                CAST(NEW.seller_id AS TEXT)
            ) ON CONFLICT(id_reuniao) DO UPDATE SET
                titulo_reuniao = excluded.titulo_reuniao,
                estagio_negociacao = excluded.estagio_negociacao;

            INSERT INTO tb_transcricoes (
                id_transcricoes, texto_completo, palavras_chave,
                sentimento_geral, data_transcricao, tb_reuniao_id_reuniao
            ) VALUES (
                CAST(NEW.id AS TEXT),
                COALESCE((
                    SELECT group_concat(json_extract(message.value, '$.text'), char(10))
                    FROM json_each(NEW.transcript_json) AS message
                ), NEW.transcript_json),
                COALESCE((
                    SELECT group_concat(json_extract(keyword.value, '$.term'), ', ')
                    FROM json_each(NEW.summary_json, '$.key_terms') AS keyword
                ), ''),
                ROUND(COALESCE(json_extract(
                    NEW.summary_json, '$.sentiment_score'
                ), 0) / 100.0, 3),
                date(NEW.created_at), CAST(NEW.id AS TEXT)
            ) ON CONFLICT(id_transcricoes) DO UPDATE SET
                texto_completo = excluded.texto_completo,
                palavras_chave = excluded.palavras_chave,
                sentimento_geral = excluded.sentimento_geral;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_torus_meetings_organizacao_update
        AFTER UPDATE OF title, summary_json, transcript_json, customer_id, seller_id
        ON meetings
        BEGIN
            UPDATE tb_reuniao SET
                titulo_reuniao = NEW.title,
                estagio_negociacao = COALESCE((
                    SELECT stage FROM customers WHERE id=NEW.customer_id
                ), ''),
                tb_cliente_id_cliente = CAST(NEW.customer_id AS TEXT),
                tb_vendedor_id_vendedor = CAST(NEW.seller_id AS TEXT)
            WHERE id_reuniao = CAST(NEW.id AS TEXT);

            UPDATE tb_transcricoes SET
                texto_completo = COALESCE((
                    SELECT group_concat(json_extract(message.value, '$.text'), char(10))
                    FROM json_each(NEW.transcript_json) AS message
                ), NEW.transcript_json),
                palavras_chave = COALESCE((
                    SELECT group_concat(json_extract(keyword.value, '$.term'), ', ')
                    FROM json_each(NEW.summary_json, '$.key_terms') AS keyword
                ), ''),
                sentimento_geral = ROUND(COALESCE(json_extract(
                    NEW.summary_json, '$.sentiment_score'
                ), 0) / 100.0, 3)
            WHERE id_transcricoes = CAST(NEW.id AS TEXT);
        END;

        CREATE TRIGGER IF NOT EXISTS trg_torus_tasks_organizacao_insert
        AFTER INSERT ON tasks
        BEGIN
            INSERT INTO tb_tarefa (
                id_tarefa, titulo_tarefa, descricao_tarefa, data_prazo,
                prioridade_tarefa, status_tarefa, data_criacao,
                data_conclusao, tb_cliente_id_cliente,
                tb_vendedor_id_vendedor, tb_reuniao_id_reuniao
            ) VALUES (
                CAST(NEW.id AS TEXT), NEW.title, NEW.notes, NEW.due_date,
                CASE NEW.priority WHEN 'high' THEN 'Alta' ELSE 'Normal' END,
                CASE NEW.status WHEN 'done' THEN 'Concluída' ELSE 'Pendente' END,
                NEW.created_at, NEW.completed_at, CAST(NEW.customer_id AS TEXT),
                CAST((
                    SELECT seller_id FROM customers WHERE id=NEW.customer_id
                ) AS TEXT),
                CASE WHEN NEW.meeting_id IS NULL THEN NULL
                     ELSE CAST(NEW.meeting_id AS TEXT) END
            ) ON CONFLICT(id_tarefa) DO UPDATE SET
                titulo_tarefa = excluded.titulo_tarefa,
                descricao_tarefa = excluded.descricao_tarefa,
                data_prazo = excluded.data_prazo,
                prioridade_tarefa = excluded.prioridade_tarefa,
                status_tarefa = excluded.status_tarefa,
                data_conclusao = excluded.data_conclusao,
                tb_cliente_id_cliente = excluded.tb_cliente_id_cliente,
                tb_vendedor_id_vendedor = excluded.tb_vendedor_id_vendedor,
                tb_reuniao_id_reuniao = excluded.tb_reuniao_id_reuniao;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_torus_tasks_organizacao_update
        AFTER UPDATE OF title, notes, due_date, priority, status, completed_at,
            customer_id, meeting_id ON tasks
        BEGIN
            UPDATE tb_tarefa SET
                titulo_tarefa = NEW.title,
                descricao_tarefa = NEW.notes,
                data_prazo = NEW.due_date,
                prioridade_tarefa = CASE NEW.priority
                    WHEN 'high' THEN 'Alta' ELSE 'Normal' END,
                status_tarefa = CASE NEW.status
                    WHEN 'done' THEN 'Concluída' ELSE 'Pendente' END,
                data_conclusao = NEW.completed_at,
                tb_cliente_id_cliente = CAST(NEW.customer_id AS TEXT),
                tb_vendedor_id_vendedor = CAST((
                    SELECT seller_id FROM customers WHERE id=NEW.customer_id
                ) AS TEXT),
                tb_reuniao_id_reuniao = CASE WHEN NEW.meeting_id IS NULL THEN NULL
                    ELSE CAST(NEW.meeting_id AS TEXT) END
            WHERE id_tarefa = CAST(NEW.id AS TEXT);
        END;
        """
    )

    connection.execute(
        """INSERT INTO tb_vendedor (
               id_vendedor,nome_vendedor,email_vendedor,equipe_vendedor
           ) SELECT CAST(id AS TEXT),name,email,'Comercial'
             FROM users WHERE role='seller'
           ON CONFLICT(id_vendedor) DO UPDATE SET
               nome_vendedor=excluded.nome_vendedor,
               email_vendedor=excluded.email_vendedor"""
    )
    connection.execute(
        """INSERT INTO tb_cliente (
               id_cliente,nome_cliente,tipo_empresa_cliente,
               data_cadastro_cliente,telefone_cliente
           ) SELECT CAST(id AS TEXT),name,segment,date(created_at),''
             FROM customers WHERE 1
           ON CONFLICT(id_cliente) DO UPDATE SET
               nome_cliente=excluded.nome_cliente,
               tipo_empresa_cliente=excluded.tipo_empresa_cliente"""
    )
    connection.execute(
        """INSERT INTO tb_reuniao (
               id_reuniao,titulo_reuniao,data_reuniao,horario_reuniao,
               duracao_reuniao,plataforma_reuniao,estagio_negociacao,
               status_negociacao,tb_cliente_id_cliente,tb_vendedor_id_vendedor
           ) SELECT CAST(m.id AS TEXT),m.title,date(m.created_at),time(m.created_at),
                    0,'Torus',c.stage,'Analisada',CAST(c.id AS TEXT),
                    CAST(m.seller_id AS TEXT)
             FROM meetings m JOIN customers c ON c.id=m.customer_id WHERE 1
           ON CONFLICT(id_reuniao) DO UPDATE SET
               titulo_reuniao=excluded.titulo_reuniao,
               estagio_negociacao=excluded.estagio_negociacao"""
    )
    connection.execute(
        """INSERT INTO tb_transcricoes (
               id_transcricoes,texto_completo,palavras_chave,
               sentimento_geral,data_transcricao,tb_reuniao_id_reuniao
           ) SELECT CAST(m.id AS TEXT),
                    COALESCE((
                        SELECT group_concat(
                            json_extract(message.value,'$.text'),char(10)
                        ) FROM json_each(m.transcript_json) AS message
                    ),m.transcript_json),
                    COALESCE((
                        SELECT group_concat(
                            json_extract(keyword.value,'$.term'),', '
                        ) FROM json_each(m.summary_json,'$.key_terms') AS keyword
                    ),''),
                    ROUND(COALESCE(json_extract(
                        m.summary_json,'$.sentiment_score'
                    ),0)/100.0,3),
                    date(m.created_at),CAST(m.id AS TEXT)
             FROM meetings m WHERE 1
           ON CONFLICT(id_transcricoes) DO UPDATE SET
               texto_completo=excluded.texto_completo,
               palavras_chave=excluded.palavras_chave,
               sentimento_geral=excluded.sentimento_geral"""
    )
    connection.execute(
        """INSERT INTO tb_tarefa (
               id_tarefa,titulo_tarefa,descricao_tarefa,data_prazo,
               prioridade_tarefa,status_tarefa,data_criacao,data_conclusao,
               tb_cliente_id_cliente,tb_vendedor_id_vendedor,
               tb_reuniao_id_reuniao
           ) SELECT CAST(t.id AS TEXT),t.title,t.notes,t.due_date,
                    CASE t.priority WHEN 'high' THEN 'Alta' ELSE 'Normal' END,
                    CASE t.status WHEN 'done' THEN 'Concluída' ELSE 'Pendente' END,
                    t.created_at,t.completed_at,CAST(t.customer_id AS TEXT),
                    CAST(c.seller_id AS TEXT),
                    CASE WHEN t.meeting_id IS NULL THEN NULL
                         ELSE CAST(t.meeting_id AS TEXT) END
             FROM tasks t JOIN customers c ON c.id=t.customer_id WHERE 1
           ON CONFLICT(id_tarefa) DO UPDATE SET
               titulo_tarefa=excluded.titulo_tarefa,
               descricao_tarefa=excluded.descricao_tarefa,
               data_prazo=excluded.data_prazo,
               prioridade_tarefa=excluded.prioridade_tarefa,
               status_tarefa=excluded.status_tarefa,
               data_conclusao=excluded.data_conclusao,
               tb_cliente_id_cliente=excluded.tb_cliente_id_cliente,
               tb_vendedor_id_vendedor=excluded.tb_vendedor_id_vendedor,
               tb_reuniao_id_reuniao=excluded.tb_reuniao_id_reuniao"""
    )
