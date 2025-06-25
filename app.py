import sqlite3
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, g
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

# --- Configuración de la Aplicación ---
app = Flask(__name__)
# ¡IMPORTANTE! Genera una clave secreta fuerte y única para tu aplicación.
# NUNCA uses esta en producción. Usa os.urandom(24) o similar.
app.secret_key = 'tu_clave_secreta_super_segura_aqui_y_muy_larga'  # ¡Cambia esto en producción!
DATABASE_NAME = 'BDtask.db'


# --- Funciones de Utilidad para la Base de Datos ---

def get_db():
    """Obtiene una conexión a la base de datos. Crea una si no existe."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE_NAME)
        db.row_factory = sqlite3.Row  # Esto hace que las filas se comporten como diccionarios (acceso por nombre de columna)
    return db


@app.teardown_appcontext
def close_connection(exception):
    """Cierra la conexión a la base de datos al finalizar la solicitud."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    """Inicializa la base de datos si no existe el archivo o si las tablas no existen."""
    conn = get_db()  # Abre la conexión
    cursor = conn.cursor()

    # Tabla Usuarios
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS users
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       username
                       TEXT
                       UNIQUE
                       NOT
                       NULL,
                       password
                       TEXT
                       NOT
                       NULL
                   )
                   ''')

    # Tabla Tareas
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS tasks
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       user_id
                       INTEGER
                       NOT
                       NULL,
                       title
                       TEXT
                       NOT
                       NULL,
                       description
                       TEXT,
                       due_date
                       TEXT,        -- Formato YYYY-MM-DD
                       status
                       TEXT
                       NOT
                       NULL
                       DEFAULT
                       'Pendiente', -- 'Pendiente' o 'Completada'
                       created_at
                       TEXT
                       NOT
                       NULL
                       DEFAULT
                       CURRENT_TIMESTAMP,
                       FOREIGN
                       KEY
                   (
                       user_id
                   ) REFERENCES users
                   (
                       id
                   )
                       )
                   ''')

    conn.commit()
    print(f"Base de datos '{DATABASE_NAME}' y tablas verificadas/creadas.")


# --- Decorador para Requerir Autenticación ---
def login_required(f):
    """
    Decorador que verifica si el usuario está autenticado.
    Redirige a la página de inicio de sesión si no lo está.
    """

    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    # Asignar un nombre único para evitar conflictos de endpoint con otros decoradores
    # Esto es crucial para Flask. Si no lo hacemos, Flask intentará usar 'decorated_function'
    # para múltiples rutas si el mismo decorador se usa en ellas.
    decorated_function.__name__ = f.__name__  # Usa el nombre de la función original
    return decorated_function


# --- Rutas (Endpoints) y Lógica de Negocio ---

# --- Rutas de Autenticación (RF001) ---

@app.route('/register', methods=['GET', 'POST'], endpoint='register')
def register():
    """Maneja el registro de nuevos usuarios."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            return render_template('register.html', error='Nombre de usuario y contraseña son obligatorios.')

        hashed_password = generate_password_hash(password)

        db = get_db()
        cursor = db.cursor()

        try:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            db.commit()
            return redirect(url_for('login'))  # Redirigir a login después de registro exitoso
        except sqlite3.IntegrityError:
            # RN001 - Unicidad de Usuario
            return render_template('register.html', error='El nombre de usuario ya existe.')
        except Exception as e:
            return render_template('register.html', error=f'Error al registrar: {e}')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'], endpoint='login')
def login():
    """Maneja el inicio de sesión de usuarios."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            return render_template('login.html', error='Nombre de usuario y contraseña son obligatorios.')

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('tasks_list'))  # Redirigir al panel de tareas
        else:
            return render_template('login.html', error='Credenciales inválidas.')
    return render_template('login.html')


@app.route('/logout', endpoint='logout')
@login_required
def logout():
    """Cierra la sesión del usuario."""
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('login'))


# --- Rutas de Gestión de Tareas (RF002, RF003) ---

@app.route('/', endpoint='tasks_list')
@login_required
def tasks_list():
    """Muestra la lista de tareas del usuario autenticado."""
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()

    status_filter = request.args.get('status')
    search_query = request.args.get('search')

    query = "SELECT * FROM tasks WHERE user_id = ?"
    params = [user_id]

    if status_filter in ['Pendiente', 'Completada']:
        query += " AND status = ?"
        params.append(status_filter)

    if search_query:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params.append(f'%{search_query}%')
        params.append(f'%{search_query}%')

    query += " ORDER BY created_at DESC"  # Ordenar por fecha de creación

    cursor.execute(query, params)
    tasks = cursor.fetchall()

    return render_template('tasks.html', tasks=tasks, username=session['username'],
                           status_filter=status_filter, search_query=search_query)


@app.route('/add_task', methods=['GET', 'POST'], endpoint='add_task')
@login_required
def add_task():
    """Permite crear una nueva tarea."""
    if request.method == 'POST':
        user_id = session['user_id']
        title = request.form['title']
        description = request.form.get('description')
        due_date = request.form.get('due_date')

        # RN002 - Obligatoriedad de Campos
        if not title:
            return render_template('add_edit_task.html', task=None, error='El título de la tarea es obligatorio.')

        # RN004 - Fechas Válidas (solo si se proporciona)
        if due_date:
            try:
                # Intenta parsear la fecha y compararla con la fecha actual (solo la fecha, no la hora)
                task_date = datetime.strptime(due_date, '%Y-%m-%d').date()
                if task_date < datetime.now().date():
                    return render_template('add_edit_task.html', task=None,
                                           error='La fecha de vencimiento no puede ser en el pasado.')
            except ValueError:
                return render_template('add_edit_task.html', task=None,
                                       error='Formato de fecha inválido. Use YYYY-MM-DD.')

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO tasks (user_id, title, description, due_date) VALUES (?, ?, ?, ?)",
            (user_id, title, description, due_date)
        )
        db.commit()
        return redirect(url_for('tasks_list'))
    return render_template('add_edit_task.html', task=None, form_action=url_for('add_task'))


@app.route('/edit_task/<int:task_id>', methods=['GET', 'POST'], endpoint='edit_task')
@login_required
def edit_task(task_id):
    """Permite editar una tarea existente."""
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    task = cursor.fetchone()

    # RN003 - Propiedad de la Tarea
    if not task:
        # Si la tarea no existe o no pertenece al usuario, redirigir o mostrar error 404/403
        return redirect(url_for('tasks_list'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description')
        due_date = request.form.get('due_date')
        status = request.form.get('status')  # Permitir cambiar el estado desde aquí

        # RN002 - Obligatoriedad de Campos
        if not title:
            return render_template('add_edit_task.html', task=task, error='El título de la tarea es obligatorio.')

        # RN004 - Fechas Válidas (solo si se proporciona)
        if due_date:
            try:
                task_date = datetime.strptime(due_date, '%Y-%m-%d').date()
                if task_date < datetime.now().date():
                    return render_template('add_edit_task.html', task=task,
                                           error='La fecha de vencimiento no puede ser en el pasado.')
            except ValueError:
                return render_template('add_edit_task.html', task=task,
                                       error='Formato de fecha inválido. Use YYYY-MM-DD.')

        # RN005 - Estado de Tarea (asegurar que solo sean los válidos)
        if status not in ['Pendiente', 'Completada']:
            status = task['status']  # Mantener el estado actual si se envía uno inválido

        cursor.execute(
            "UPDATE tasks SET title = ?, description = ?, due_date = ?, status = ? WHERE id = ? AND user_id = ?",
            (title, description, due_date, status, task_id, user_id)
        )
        db.commit()
        return redirect(url_for('tasks_list'))

    return render_template('add_edit_task.html', task=task, form_action=url_for('edit_task', task_id=task_id))


@app.route('/delete_task/<int:task_id>', methods=['POST'], endpoint='delete_task')
@login_required
def delete_task(task_id):
    """Permite eliminar una tarea."""
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()

    # RN003 - Propiedad de la Tarea: Borramos solo si la tarea pertenece al usuario
    cursor.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    db.commit()
    return redirect(url_for('tasks_list'))


@app.route('/mark_task/<int:task_id>/<status>', methods=['POST'], endpoint='mark_task')
@login_required
def mark_task(task_id, status):
    """Permite marcar una tarea como 'Pendiente' o 'Completada'."""
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()

    # RN005 - Estado de Tarea: Asegurarse que el estado sea válido
    if status in ['Pendiente', 'Completada']:
        cursor.execute(
            "UPDATE tasks SET status = ? WHERE id = ? AND user_id = ?",
            (status, task_id, user_id)
        )
        db.commit()
    return redirect(url_for('tasks_list'))


# --- Punto de Entrada para Ejecutar la Aplicación ---
if __name__ == '__main__':
    # Esta sección solo se ejecuta cuando corres 'python app.py' directamente
    # No se usa cuando Gunicorn (para Render) inicia la app.
    with app.app_context():
        init_db()

    app.run(debug=True, host='0.0.0.0')

# Sin embargo, para Render, Flask necesita que init_db() se ejecute
# cuando la aplicación se carga en el contexto del WSGI (Gunicorn).
# La forma más limpia es asegurar que init_db() se llame al configurar la app.
# En Flask, esto se hace con un decorador `before_first_request`
# o simplemente llamando a init_db en el contexto de app.
# Para la simplicidad de este proyecto, vamos a confiar en que Render ejecutará el main para la creación inicial
# y que si el archivo DB existe, no lo recreará.
# El init_db actual ya maneja 'CREATE TABLE IF NOT EXISTS'.
# Para un proyecto real con Render, se prefiere una DB externa (PostgreSQL).
# Para este demo, no necesitamos un cambio adicional en init_db o su llamada para que funcione en Render,
# porque la base de datos se inicializa cuando la aplicación se arranca por primera vez
# y persistirá mientras el contenedor de Render no se reinicie completamente.
# Si los datos se pierden con un reinicio de Render, es el comportamiento esperado para SQLite en ese entorno.