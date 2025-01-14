import os
import sys
import uvicorn
from manage_db import recreate_database
import logging

# Set the logging level for all SQLAlchemy loggers
logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.engine.Engine').setLevel(logging.WARNING)

def main():
    # Check if we need to recreate the database
    if len(sys.argv) > 1 and sys.argv[1] == '--recreate-db':
        print("Recreating database...")
        recreate_database()
    
    # Start the FastAPI application
    print("Starting application...")
    uvicorn.run(
        "src.chat_system.api.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )

if __name__ == "__main__":
    main() 