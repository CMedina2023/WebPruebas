import sqlite3

DATABASE_NAME = 'BDtask.db'

def create_database():
    """Crea la base de datos SQLite y las tablas de Usuarios y Tareas."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Tabla Usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    # Tabla Tareas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT, -- Formato YYYY-MM-DD
            status TEXT NOT NULL DEFAULT 'Pendiente', -- 'Pendiente' o 'Completada'
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()
    print(f"Base de datos '{DATABASE_NAME}' y tablas creadas exitosamente.")

if __name__ == '__main__':
    create_database()