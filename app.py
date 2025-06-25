import sqlite3
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, g
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

# --- Configuración de la Aplicación Flask ---
# La instancia de la aplicación Flask debe ser lo primero en definirse después de las importaciones.
app = Flask(__name__)

# ¡IMPORTANTE! Genera una clave secreta fuerte y única para tu aplicación.
# NUNCA uses esta en producción directamente en el código.
# La obtenemos de una variable de entorno 'SECRET_KEY' (para Render)
# o usamos una por defecto para desarrollo local (que no sea segura para producción).
app.secret_key = os.environ.get('SECRET_KEY', 'una_clave_super_secreta_y_larga_para_desarrollo_local_NO_USAR_EN_PRODUCCION_REAL') 

DATABASE_NAME = 'taskflow.db' # Define el nombre de la base de datos.


# --- Funciones de Utilidad para la Base de Datos ---
# Estas funciones (incluyendo aquellas con decoradores de 'app')
# deben definirse DESPUÉS de que 'app' haya sido instanciada.

def get_db():
    """
    Obtiene una conexión a la base de datos.
    Crea una nueva conexión si no existe en el objeto 'g' de Flask.
    Usa 'sqlite3.Row' para que los resultados de las consultas se comporten como diccionarios,
    permitiendo acceder a las columnas por su nombre.
    """
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE_NAME)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """
    Cierra la conexión a la base de datos cuando el contexto de la aplicación
    finaliza (ej. al terminar una solicitud web).
    """
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """
    Crea las tablas 'users' y 'tasks' en la base de datos si no existen.
    Esta función es idempotente, es decir, puede llamarse varias veces sin causar errores
    si las tablas ya existen.
    """
    conn = get_db() # Obtiene una conexión a la base de datos.
    cursor = conn.cursor()
    
    # Crea la tabla 'users' si no existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    # Crea la tabla 'tasks' si no existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT, -- Formatoั้น-MM-DD
            status TEXT NOT NULL DEFAULT 'Pendiente', -- 'Pendiente' o 'Completada'
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit() # Guarda los cambios en la base de datos.
    print(f"Base de datos '{DATABASE_NAME}' y tablas verificadas/creadas.")

# Aseguramos que la base de datos y las tablas se inicialicen
# Esto se ejecuta cuando la aplicación se carga por Gunicorn (en Render) o localmente.
# Es crucial que se haga dentro de un contexto de aplicación.
with app.app_context():
    # init_db() ya está definida en este punto.
    init_db()

# --- Decorador para Requerir Autenticación ---
def login_required(f):
    """
    Decorador personalizado que verifica si el usuario ha iniciado sesión.
    Si el 'user_id' no está en la sesión de Flask, redirige al usuario a la página de login.
    """
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    
    # Asignar un nombre único a la función decorada es crucial para Flask.
    # Evita el error 'View function mapping is overwriting an existing endpoint function'.
    # Usamos el nombre de la función original para el endpoint.
    decorated_function.__name__ = f.__name__ 
    return decorated_function


# --- Rutas (Endpoints) y Lógica de Negocio ---

# --- Rutas de Autenticación (RF001) ---

@app.route('/register', methods=['GET', 'POST'], endpoint='register')
def register():
    """
    Maneja el registro de nuevos usuarios.
    - GET: Muestra el formulario de registro.
    - POST: Procesa el envío del formulario.
        - Valida que usuario y contraseña no estén vacíos.
        - Hashea la contraseña para seguridad.
        - Intenta insertar el nuevo usuario en la base de datos.
        - Si el nombre de usuario ya existe (IntegrityError), muestra un error.
        - Redirige al login si el registro es exitoso.
    """
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # RN002 - Obligatoriedad de Campos (para registro)
        if not username or not password:
            return render_template('register.html', error='Nombre de usuario y contraseña son obligatorios.')

        hashed_password = generate_password_hash(password)

        db = get_db()
        cursor = db.cursor()

        try:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            db.commit()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            # RN001 - Unicidad de Usuario
            return render_template('register.html', error='El nombre de usuario ya existe.')
        except Exception as e:
            # Captura otros posibles errores durante el registro.
            return render_template('register.html', error=f'Error al registrar: {e}')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'], endpoint='login')
def login():
    """
    Maneja el inicio de sesión de usuarios.
    - GET: Muestra el formulario de login.
    - POST: Procesa el envío del formulario.
        - Valida que usuario y contraseña no estén vacíos.
        - Busca el usuario en la base de datos.
        - Compara la contraseña ingresada con la hasheada almacenada.
        - Si las credenciales son correctas, establece la sesión y redirige a las tareas.
        - Si no, muestra un error.
    """
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Validación de campos vacíos para login
        if not username or not password:
            return render_template('login.html', error='Nombre de usuario y contraseña son obligatorios.')

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('tasks_list'))
        else:
            return render_template('login.html', error='Credenciales inválidas.')
    return render_template('login.html')

@app.route('/logout', endpoint='logout')
@login_required # Esta ruta requiere que el usuario esté logeado para poder cerrarla.
def logout():
    """
    Cierra la sesión activa del usuario.
    Elimina 'user_id' y 'username' de la sesión y redirige a la página de login.
    """
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('login'))


# --- Rutas de Gestión de Tareas (RF002, RF003) ---

@app.route('/', endpoint='tasks_list')
@login_required # Esta ruta requiere autenticación.
def tasks_list():
    """
    Muestra la lista de tareas del usuario autenticado.
    Permite filtrar tareas por estado y buscar por título o descripción.
    """
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()

    status_filter = request.args.get('status') # Obtiene el filtro de estado de la URL (GET)
    search_query = request.args.get('search')   # Obtiene la cadena de búsqueda de la URL (GET)

    query = "SELECT * FROM tasks WHERE user_id = ?"
    params = [user_id]

    # Aplica filtro por estado si se proporciona y es válido (RN005).
    if status_filter in ['Pendiente', 'Completada']:
        query += " AND status = ?"
        params.append(status_filter)

    # Aplica búsqueda por título o descripción si se proporciona.
    if search_query:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params.append(f'%{search_query}%') # El % es un comodín para LIKE en SQL
        params.append(f'%{search_query}%')

    query += " ORDER BY created_at DESC" # Ordena las tareas por fecha de creación descendente

    cursor.execute(query, params)
    tasks = cursor.fetchall() # Obtiene todas las tareas que coinciden

    # Renderiza la plantilla 'tasks.html' pasando las tareas y otros datos.
    return render_template('tasks.html', tasks=tasks, username=session['username'],
                           status_filter=status_filter, search_query=search_query)

@app.route('/add_task', methods=['GET', 'POST'], endpoint='add_task')
@login_required # Esta ruta requiere autenticación.
def add_task():
    """
    Permite al usuario crear una nueva tarea.
    - GET: Muestra el formulario para añadir una tarea.
    - POST: Procesa el envío del formulario.
        - Valida el título (RN002).
        - Valida la fecha de vencimiento (RN004).
        - Inserta la nueva tarea en la base de datos asociada al usuario.
        - Redirige a la lista de tareas.
    """
    if request.method == 'POST':
        user_id = session['user_id']
        title = request.form['title']
        description = request.form.get('description')
        due_date = request.form.get('due_date')

        # RN002 - Obligatoriedad de Campos: El título de la tarea es obligatorio.
        if not title:
            return render_template('add_edit_task.html', task=None, error='El título de la tarea es obligatorio.', form_action=url_for('add_task'))

        # RN004 - Fechas Válidas: Si se proporciona una fecha, debe ser hoy o en el futuro.
        if due_date:
            try:
                task_date = datetime.strptime(due_date, '%Y-%m-%d').date()
                if task_date < datetime.now().date():
                    return render_template('add_edit_task.html', task=None, error='La fecha de vencimiento no puede ser en el pasado.', form_action=url_for('add_task'))
            except ValueError:
                return render_template('add_edit_task.html', task=None, error='Formato de fecha inválido. Use-MM-DD.', form_action=url_for('add_task'))

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO tasks (user_id, title, description, due_date) VALUES (?, ?, ?, ?)",
            (user_id, title, description, due_date)
        )
        db.commit()
        return redirect(url_for('tasks_list'))
    # Si es GET request, renderiza el formulario vacío para añadir.
    return render_template('add_edit_task.html', task=None, form_action=url_for('add_task'))


@app.route('/edit_task/<int:task_id>', methods=['GET', 'POST'], endpoint='edit_task')
@login_required # Esta ruta requiere autenticación.
def edit_task(task_id):
    """
    Permite al usuario editar una tarea existente.
    - GET: Muestra el formulario pre-rellenado con los datos de la tarea.
    - POST: Procesa el envío del formulario.
        - Valida que la tarea pertenezca al usuario (RN003).
        - Valida el título (RN002).
        - Valida la fecha de vencimiento (RN004).
        - Valida el estado (RN005).
        - Actualiza la tarea en la base de datos.
        - Redirige a la lista de tareas.
    """
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    task = cursor.fetchone()

    # RN003 - Propiedad de la Tarea: Si la tarea no existe o no pertenece al usuario, redirige.
    if not task:
        return redirect(url_for('tasks_list'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description')
        due_date = request.form.get('due_date')
        status = request.form.get('status')

        # RN002 - Obligatoriedad de Campos
        if not title:
            return render_template('add_edit_task.html', task=task, error='El título de la tarea es obligatorio.', form_action=url_for('edit_task', task_id=task_id))

        # RN004 - Fechas Válidas
        if due_date:
            try:
                task_date = datetime.strptime(due_date, '%Y-%m-%d').date()
                if task_date < datetime.now().date():
                    return render_template('add_edit_task.html', task=task, error='La fecha de vencimiento no puede ser en el pasado.', form_action=url_for('edit_task', task_id=task_id))
            except ValueError:
                return render_template('add_edit_task.html', task=task, error='Formato de fecha inválido. Use-MM-DD.', form_action=url_for('edit_task', task_id=task_id))

        # RN005 - Estado de Tarea: Asegura que el estado sea 'Pendiente' o 'Completada'.
        if status not in ['Pendiente', 'Completada']:
            status = task['status'] # Mantiene el estado actual si se envía uno inválido

        cursor.execute(
            "UPDATE tasks SET title = ?, description = ?, due_date = ?, status = ? WHERE id = ? AND user_id = ?",
            (title, description, due_date, status, task_id, user_id)
        )
        db.commit()
        return redirect(url_for('tasks_list'))

    # Si es GET request, renderiza el formulario con los datos de la tarea para editar.
    return render_template('add_edit_task.html', task=task, form_action=url_for('edit_task', task_id=task_id))


@app.route('/delete_task/<int:task_id>', methods=['POST'], endpoint='delete_task')
@login_required # Esta ruta requiere autenticación.
def delete_task(task_id):
    """
    Permite al usuario eliminar una tarea.
    - POST: Procesa la solicitud de eliminación.
        - Asegura que la tarea pertenezca al usuario (RN003).
        - Elimina la tarea de la base de datos.
        - Redirige a la lista de tareas.
    """
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()

    # RN003 - Propiedad de la Tarea: Elimina la tarea solo si pertenece al usuario actual.
    cursor.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    db.commit()
    return redirect(url_for('tasks_list'))

@app.route('/mark_task/<int:task_id>/<status>', methods=['POST'], endpoint='mark_task')
@login_required # Esta ruta requiere autenticación.
def mark_task(task_id, status):
    """
    Permite al usuario marcar una tarea como 'Pendiente' o 'Completada'.
    - POST: Procesa la solicitud para cambiar el estado.
        - Asegura que la tarea pertenezca al usuario (RN003).
        - Valida que el estado sea 'Pendiente' o 'Completada' (RN005).
        - Actualiza el estado de la tarea en la base de datos.
        - Redirige a la lista de tareas.
    """
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()

    # RN005 - Estado de Tarea: Asegura que el estado sea válido.
    if status in ['Pendiente', 'Completada']:
        cursor.execute(
            "UPDATE tasks SET status = ? WHERE id = ? AND user_id = ?",
            (status, task_id, user_id)
        )
        db.commit()
    return redirect(url_for('tasks_list'))

# --- Punto de Entrada para Ejecutar la Aplicación ---
if __name__ == '__main__':
    # Esta sección solo se ejecuta cuando corres 'python app.py' directamente (desarrollo local).
    # La inicialización de la DB ya se maneja arriba en el ámbito global del módulo,
    # asegurando que se ejecute una vez al cargar la aplicación, ya sea localmente o con Gunicorn.
    
    # app.run(debug=True) es solo para desarrollo.
    # host='0.0.0.0' permite que sea accesible desde otras máquinas en la red local.
    # Render gestiona su propio puerto, no usamos un puerto fijo aquí para producción.
    app.run(debug=True, host='0.0.0.0')
