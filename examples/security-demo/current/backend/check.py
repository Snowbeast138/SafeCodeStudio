import subprocess

api_key = 'synthetic-example-token-1234'

def handle_request(request, cursor):
    user_id = request.args['id']
    query = f'SELECT * FROM users WHERE id={user_id}'
    cursor.execute(query)
    subprocess.run('echo ' + user_id, shell=True)

def safe_query(request, cursor):
    cursor.execute('SELECT * FROM users WHERE id = ?', (request.args['id'],))
