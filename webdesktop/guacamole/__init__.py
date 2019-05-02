import logging

from quart import (
    abort,
    current_app, render_template, Blueprint, request, websocket
)
import trio

from .client import GuacamoleClient

logger = logging.getLogger('guacamole')
logger.setLevel(logging.DEBUG)


bp = Blueprint('guacamole', __name__,
    url_prefix='/guacamole',
    static_folder='static',
    template_folder='templates')


def init_app(app):
    app.register_blueprint(bp)


@bp.route('/')
async def index():
    return await render_template('index.html')


# guacd daemon host address and port
GUACD_HOST = '127.0.0.1'
GUACD_PORT = 4822
GUACD_TIMEOUT = 20

# ssh login settings
SSH_HOST = 'sshd'
SSH_PORT = 22
SSH_USER = 'root'
SSH_PASSWORD = 'gugus'

async def ws_receive(guac_client):
    while True:
        data = await websocket.receive()
        logger.info('client-to-server %s', data)
        await guac_client.send(data)


async def ws_send(guac_client):
    while True:
        data = await guac_client.receive()
        logger.info('server-to-client %s', data)
        if data:
            await websocket.send(data)
        else:
            break
    # End-of-instruction marker
    await websocket.send('0.;')


@bp.websocket('/ws')
async def ws():

    with trio.move_on_after(GUACD_TIMEOUT) as cancel_scope:
        try:
            guac_socket = await trio.open_tcp_stream(GUACD_HOST, GUACD_PORT)
            logger.debug('Client connected with guacd server (%s:%s)'
                          % (GUACD_HOST, GUACD_PORT))
        except OSError as e:
            abort(500)
    print("timed out: %s" % cancel_scope.cancelled_caught)
    if cancel_scope.cancelled_caught:
        abort(500)

    guac_client = GuacamoleClient(guac_socket, debug=True, logger=logger)
    await guac_client.handshake(protocol='ssh',
                 hostname=SSH_HOST,
                 port=SSH_PORT,
                 username=SSH_USER,
                 password=SSH_PASSWORD)

    async with trio.open_nursery() as nursery:
        nursery.start_soon(ws_receive, guac_client)
        nursery.start_soon(ws_send, guac_client)


@bp.websocket('/ws-echo')
async def ws_echo():
    while True:
        data = await websocket.receive()
        print(data)
        await websocket.send(data)