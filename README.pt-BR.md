# API de Recebimento de Eventos

Serviço em FastAPI que recebe eventos via webhook e garante que nenhum se perca
nem seja processado duas vezes.

> 🇺🇸 [Read in English](README.md)

## Status

🚧 Em desenvolvimento. O fluxo principal (recebimento, idempotência, fila,
worker com retentativas e fila de mensagens mortas) está implementado e coberto
por testes de integração.

## Problema

Quem envia webhooks faz reenvios quando não recebe resposta a tempo, então o
mesmo evento pode chegar mais de uma vez. Filas garantem entrega "pelo menos
uma vez", o que também gera cópias. E se o processamento falhar depois de a API
já ter respondido `200`, o remetente não reenvia e o evento se perde.

Este serviço trata os dois casos:

- **Duplicidade:** cada evento tem um id único vindo do remetente, guardado como
  chave primária. Um evento repetido é confirmado sem ser processado de novo.
- **Perda:** o evento é persistido antes de a API responder. Falhas no
  processamento são registradas e retentadas pelo worker, e os eventos que
  esgotam as tentativas ficam numa fila de mensagens mortas para investigação.

## Arquitetura

```
Remetente ──POST /webhook──▶ API ──insert (idempotente)──▶ PostgreSQL
                              │
                              └──publica id──▶ RabbitMQ: events.incoming
                                                    │
                                                    ▼
                                                 Worker
                                    claim (pending → processing)
                                                    │
                            ┌───────────────────────┴──────────────┐
                            ▼                                      ▼
                    processed (sucesso)            retentativa com backoff (30s, 60s)
                                                          │ após 3 tentativas
                                                          ▼
                                            failed + RabbitMQ: events.dead_letter
```

Decisões principais:

- **Idempotência no banco.** Uma `PRIMARY KEY` sobre o id do remetente faz o
  `INSERT ... ON CONFLICT DO NOTHING` decidir duplicidades de forma atômica, sem
  depender de condições de corrida no código da aplicação.
- **Duplicados retornam `202` com `status: "duplicate"`.** Um status de erro
  faria o remetente reenviar indefinidamente.
- **Só eventos novos são publicados.** O `RETURNING` informa à API se a linha
  foi inserida.
- **A mensagem carrega só o id.** O banco é a fonte da verdade; o worker lê o
  payload dele.
- **Claim com `UPDATE` condicional.** Um worker só processa um evento se
  conseguir mudar o status de `pending` (vencido) ou de `processing` expirado
  para `processing`. Dois workers não podem pegar o mesmo evento.
- **O banco agenda as retentativas.** Um loop de consulta pega eventos
  `pending` cujo `next_attempt_at` já passou. O mesmo loop cobre eventos que
  nunca chegaram à fila.
- **Fila de mensagens mortas pelo estado.** Após 3 tentativas, o evento vira
  `failed` com o último erro gravado, e o id é publicado em `events.dead_letter`.

## Stack

- Python 3.11+
- FastAPI e Pydantic v2
- SQLAlchemy 2.0 e psycopg2
- PostgreSQL 16
- RabbitMQ 3 (com painel de gestão)
- pika
- pytest e httpx
- Docker Compose

## Estrutura do projeto

```
src/
├── api/          # rotas FastAPI e schemas de entrada/saída
├── core/         # configuração
├── db/           # engine, sessão, modelo ORM
├── services/     # claim, retentativa, publicação, processamento
└── workers/      # consumidor do RabbitMQ e loop de consulta
docs/
└── schema.sql    # schema do banco, aplicado na primeira subida do container
tests/
└── integration/  # testes de API, claim, retentativa e webhook
```

## Como rodar localmente

### 1. Suba o PostgreSQL e o RabbitMQ

Requer Docker Desktop.

```bash
cp .env.example .env
docker compose up -d
```

O `schema.sql` roda automaticamente na primeira vez que o volume do PostgreSQL
é criado.

### 2. Instale as dependências

```bash
python -m venv .venv
source .venv/bin/activate        # Windows (cmd): .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Defina as variáveis de ambiente

A API e o worker leem estas variáveis do ambiente (o arquivo `.env` é usado
pelo Docker Compose, não pelo Python):

```bash
export DATABASE_URL=postgresql+psycopg2://events:change_me@localhost:5432/events_db
export RABBITMQ_URL=amqp://guest:guest@localhost:5672/
```

No Windows (`cmd`), use `set NOME=valor` no lugar de `export`.

### 4. Suba os serviços

Use três terminais, cada um com as variáveis acima:

```bash
# Terminal 1: API
uvicorn src.main:app --reload

# Terminal 2: worker
python -m src.workers.event_consumer
```

Envie um evento em `http://localhost:8000/docs` (`POST /webhook`):

```json
{
  "id": "evt_001",
  "type": "payment.received",
  "occurred_at": "2026-10-27T10:00:00Z",
  "data": {"amount": 100}
}
```

Resposta esperada: `202` com `{"id": "evt_001", "status": "accepted"}`.
Enviando o mesmo corpo de novo, a resposta traz `"status": "duplicate"`.

Para conferir o resultado:

- **Banco:** `docker compose exec postgres psql -U events -d events_db -c "SELECT id, status, attempts FROM events;"`
- **RabbitMQ:** `http://localhost:15672` (usuário e senha `guest`), filas
  `events.incoming` e `events.dead_letter`.

## Como rodar os testes

```bash
pytest -v
```

A suíte usa um banco separado, `events_test`. Ele é apagado e recriado a partir
de `docs/schema.sql` no início de cada execução, então nunca toca nos dados de
desenvolvimento.

## Limitações conhecidas

- Mudanças de schema só valem para volumes novos. Bancos existentes precisam de
  um `ALTER TABLE` manual (ou `docker compose down -v` em desenvolvimento).
- A etapa de processamento é um stub que apenas registra o evento.
- A publicação no RabbitMQ abre uma conexão nova por mensagem. Em produção,
  reutilizaríamos a conexão e usaríamos publisher confirms.
- O id duplicado não é comparado com o payload: um remetente que reutiliza o id
  para outro corpo recebe `duplicate`.
- A validação de assinatura HMAC do webhook ainda não está implementada.
- O loop de consulta e o consumidor rodam no mesmo processo, sem supervisão.

## Roadmap

- Validação de assinatura HMAC em `POST /webhook`
- Job de reconciliação para eventos que não chegaram à fila (publicação falhou
  depois do commit)
- Lógica de processamento real
- Deploy (Render ou Railway) com PostgreSQL e RabbitMQ gerenciados

## Licença

MIT