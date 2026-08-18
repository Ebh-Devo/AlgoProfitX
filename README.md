# TradeEBH

TradeEBH is a trading strategy marketplace and investment platform.

## MVP

The initial MVP focuses on:

1. Strategy creators can create and deploy trading strategies.
2. Users can discover strategies and analyze their performance.
3. Users can backtest strategies.
4. Users can connect supported broker accounts.
5. Users can allocate capital to strategies.
6. TradeEBH can execute strategy signals through supported broker integrations.

## Architecture

TradeEBH initially uses a modular monolith architecture.

### Backend

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Redis
- Background workers

### Frontend

- Next.js
- TypeScript

The backend is designed as an API-first service so that the same APIs can later support both the web application and native mobile applications.

## Repository Structure

```text
TradeEBH/
│
├── backend/          Backend application
├── frontend/         Web application
├── docs/             Architecture and technical documentation
├── infrastructure/   Docker and deployment configuration
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md