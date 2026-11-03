from unittest.mock import MagicMock, patch

import pytest

import app as book_app


@pytest.fixture
def client():
    book_app.app.config.update(TESTING=True)
    return book_app.app.test_client()


@pytest.fixture
def database():
    connection = MagicMock()
    cursor = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    with patch.object(book_app, 'get_connection', return_value=connection) as connect:
        yield cursor, connection, connect


def test_get_connection_uses_environment():
    settings = {'DB_HOST': 'localhost', 'DB_PORT': '5432', 'DB_NAME': 'books',
                'DB_USER': 'tester', 'DB_PASSWORD': 'secret'}
    with patch.dict(book_app.os.environ, settings), patch.object(book_app.psycopg2, 'connect') as connect:
        book_app.get_connection()
    connect.assert_called_once_with(host='localhost', port='5432', dbname='books',
                                    user='tester', password='secret')


@pytest.mark.parametrize('query,expected', [('', None), ('  Мир  ', '%Мир%')])
def test_index(client, database, query, expected):
    cursor, _, _ = database
    cursor.fetchall.side_effect = [[(1, 'Мир', 'Автор', 'BK1', True)], [(1, 'Иван')], []]
    with patch.object(book_app, 'render_template', return_value='ok') as render:
        response = client.get('/', query_string={'search': query})
    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'ok'
    assert render.call_args.kwargs['search'] == query.strip()
    if expected:
        assert cursor.execute.call_args_list[0].args[1] == (expected,)
    else:
        assert 'FROM books ORDER BY id' in cursor.execute.call_args_list[0].args[0]
    assert len(cursor.execute.call_args_list) == 3


@pytest.mark.parametrize('payload', [
    {'title': '', 'author': 'A', 'inventory_number': '1'},
    {'title': 'B', 'author': '', 'inventory_number': '1'},
    {'title': 'B', 'author': 'A', 'inventory_number': ''},
])
def test_add_book_rejects_missing_fields(client, database, payload):
    cursor, _, _ = database
    assert client.post('/add', data=payload).status_code == 400
    cursor.execute.assert_not_called()


def test_add_book_success(client, database):
    cursor, _, _ = database
    response = client.post('/add', data={'title': ' Book ', 'author': ' Author ', 'inventory_number': ' 42 '})
    assert response.status_code == 302
    assert cursor.execute.call_args.args[1] == ('Book', 'Author', '42')


def test_add_reader_rejects_empty(client, database):
    cursor, _, _ = database
    assert client.post('/add_reader', data={'name': '   '}).status_code == 400
    cursor.execute.assert_not_called()


def test_add_reader_success(client, database):
    cursor, connection, _ = database
    assert client.post('/add_reader', data={'name': ' Иван '}).status_code == 302
    assert cursor.execute.call_args.args[1] == ('Иван',)
    connection.commit.assert_called_once()


@pytest.mark.parametrize('data', [{}, {'book_id': '1'}, {'reader_id': '1'}])
def test_issue_missing_selection(client, database, data):
    cursor, _, _ = database
    assert client.post('/loans/add', data=data).status_code == 400
    cursor.execute.assert_not_called()


@pytest.mark.parametrize('book,reader,status', [
    (None, None, 404),
    ((False,), None, 400),
    ((True,), None, 404),
    ((True,), (2,), 302),
])
def test_issue_book_cases(client, database, book, reader, status):
    cursor, _, _ = database
    cursor.fetchone.side_effect = [book] if not book or not book[0] else [book, reader]
    response = client.post('/loans/add', data={'book_id': '1', 'reader_id': '2'})
    assert response.status_code == status
    if status == 302:
        assert len(cursor.execute.call_args_list) == 4
        assert 'UPDATE books' in cursor.execute.call_args_list[-1].args[0]


@pytest.mark.parametrize('loan,status', [(None, 404), ((7,), 302)])
def test_return_book_cases(client, database, loan, status):
    cursor, _, _ = database
    cursor.fetchone.return_value = loan
    response = client.post('/loans/return/3')
    assert response.status_code == status
    assert len(cursor.execute.call_args_list) == (3 if loan else 1)
    if loan:
        assert cursor.execute.call_args.args[1] == (7,)
