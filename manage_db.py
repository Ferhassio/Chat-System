import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def recreate_database():
    """Drop and recreate the database"""
    try:
        # Connect to postgres database
        conn = psycopg2.connect(
            dbname="postgres",
            user="postgres",
            password="VetkaSotona666",
            host="localhost",
            port="5432"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        # Create cursor
        cur = conn.cursor()
        
        # Drop database if exists
        cur.execute("DROP DATABASE IF EXISTS chat_system")
        print("Dropped existing database")
        
        # Create database
        cur.execute("CREATE DATABASE chat_system")
        print("Created new database")
        
        # Close cursor and connection
        cur.close()
        conn.close()
        print("Database recreation completed successfully")
        
    except Exception as e:
        print("Error recreating database: {}".format(str(e)))
        raise

if __name__ == "__main__":
    recreate_database() 