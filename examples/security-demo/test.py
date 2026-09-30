from flask import Flask, request, jsonify
import sqlite3
import os

app = Flask(__name__)

# 1. EXPOSICIÓN DE CLAVES PRIVADAS
# Hardcodear credenciales o claves privadas en el código fuente es una vulnerabilidad crítica.
# Si el código fuente se filtra, la clave queda expuesta.
AWS_SECRET_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
RSA_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQ...
(Clave simulada para el ejemplo)
-----END PRIVATE KEY-----"""

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 2. INYECCIÓN SQL (SQLi)
    # Concatenar directamente la entrada del usuario en la consulta SQL permite a un atacante
    # manipular la estructura de la consulta (ej. ingresar: admin' OR '1'='1).
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    
    try:
        cursor.execute(query)
        user = cursor.fetchone()
        if user:
            return jsonify({"status": "success", "message": f"Bienvenido, {user['username']}"})
        else:
            return jsonify({"status": "error", "message": "Credenciales inválidas"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@app.route('/ping', methods=['POST'])
def ping_server():
    # 3. EJECUCIÓN DE COMANDOS (Command Injection / RCE)
    # Tomar la entrada del usuario y pasarla directamente a una función que ejecuta
    # comandos del sistema operativo (como os.system o os.popen) permite al atacante
    # encadenar comandos maliciosos (ej. ingresar: 8.8.8.8; cat /etc/passwd).
    target_ip = request.form.get('ip')
    
    # Ejecuta el comando en el sistema operativo subyacente de forma insegura
    command = f"ping -c 1 {target_ip}"
    result = os.popen(command).read()
    
    return jsonify({"output": result})

if __name__ == '__main__':
    app.run(debug=True, port=5000)