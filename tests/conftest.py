import os
import tempfile

# The shared test account creates many profiles; test_accounts checks the real limit.
os.environ.setdefault('JOBFLOW_MAX_PROFILES', '1000')
# Evidence files and browser profiles must never land in the real data/ folder.
os.environ.setdefault('JOBFLOW_DATA_DIR', tempfile.mkdtemp())

TEST_USER ={'username': 'pruebas', 'password': 'clave-de-prueba-123', 'nombre': 'Cuenta de pruebas'}


def sign_in(client):
    """Inicia sesión con la cuenta compartida de pruebas y le asigna los perfiles sin dueño."""
    credentials = {k: TEST_USER[k] for k in ('username', 'password')}
    r = client.post('/api/auth/login', json=credentials)
    if r.status_code == 401:
        r = client.post('/api/auth/register', json=TEST_USER)
    assert r.status_code in (200, 201), r.text
    unclaimed = client.get('/api/account/unclaimed').json()
    if unclaimed:
        assert client.post('/api/account/claim', json={'profile_ids': [p['id'] for p in unclaimed]}).status_code == 200
    return client
