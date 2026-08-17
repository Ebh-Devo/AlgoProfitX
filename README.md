# TradeEBH



TradEBH is a strategy marketplace and trading infrastructure platform.



## MVP



The initial MVP focuses on:



1\. Strategy creators can create and deploy trading strategies.

2\. Users can discover strategies and analyze their performance.

3\. Users can backtest strategies.

4\. Users can connect supported broker accounts.

5\. Users can allocate capital to strategies.

6\. TradEBH can execute strategy signals through supported broker integrations.



## Architecture



TradEBH will initially use a modular monolith architecture.



### Backend



\- Python

\- FastAPI

\- PostgreSQL

\- SQLAlchemy

\- Alembic

\- Redis

\- Background workers



### Frontend



\- React / Next.js

\- TypeScript



# Repository Structure



```text

backend/          Backend application

frontend/         Frontend application

docs/             Architecture and technical documentation

infrastructure/   Docker and deployment configuration

