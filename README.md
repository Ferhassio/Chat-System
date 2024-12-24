# Chat System

A system for managing Telegram bots and their messages.

## Features

- Create and manage multiple workspaces
- Add Telegram bots to workspaces
- View and respond to messages from Telegram users
- User authentication and authorization
- Real-time message updates

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```
4. Create database:
```bash
python manage_db.py
```
5. Run the application:
```bash
python run.py
```

## Project Structure

- `src/chat_system/`
  - `api/` - FastAPI application code
  - `core/` - Core functionality and configuration
  - `db/` - Database models and utilities
  - `telegram/` - Telegram bot integration

## Development

To run the application in development mode with auto-reload:

```bash
python run.py
```

To recreate the database:

```bash
python run.py --recreate-db
``` 