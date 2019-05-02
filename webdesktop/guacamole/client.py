"""
The MIT License (MIT)

Copyright (c)   2014 rescale
                2014 - 2016 Mohab Usama
"""

import logging

logger = logging.getLogger('guacamole')
# FIXME: does not belong here
logger.setLevel(logging.INFO)
logger.handlers = [logging.StreamHandler()]

from .exceptions import GuacamoleError

from .instruction import INST_TERM
from .instruction import GuacamoleInstruction as Instruction


# supported protocols
PROTOCOLS = ('vnc', 'rdp', 'ssh')

PROTOCOL_NAME = 'guacamole'

BUF_LEN = 4096


class GuacamoleClient(object):
    """Guacamole Client class."""

    def __init__(self, socket, debug=False, logger=None):
        """
        Guacamole Client class. This class can handle communication with guacd
        server.

        :param host: guacd server host.

        :param port: guacd server port.

        :param timeout: socket connection timeout.

        :param debug: if True, default logger will switch to Debug level.
        """
        self.socket = socket

        # handshake established?
        self.connected = False

        self.delimiter = INST_TERM.encode()
        self.delimiter_size = len(self.delimiter)

        # Receiving buffer
        self._buffer = bytearray()

        # Client ID
        self._id = None

        self.logger = logger or logging.getLogger('guacamole')

        # FIXME: does not belong here
        if debug:
            self.logger.setLevel(logging.DEBUG)

    @property
    def id(self):
        """Return client id"""
        return self._id

    async def close(self):
        """
        Terminate connection with Guacamole guacd server.
        """
        await self.socket.aclose()
        self._client = None
        self.connected = False
        self.logger.debug('Connection closed.')

    async def receive(self):
        """
        Receive instructions from Guacamole guacd server.
        """
        offset = 0
        while True:
            # Check if the delimiter can be found in the current buffer.
            index = self._buffer.find(self.delimiter, offset)
            if index >= 0:
                # A instruction was fully received!
                # Remove it from the buffer and return it.
                instruction_size = index + self.delimiter_size
                instruction = self._buffer[:instruction_size]
                del self._buffer[:instruction_size]
                instruction = instruction.decode()
                self.logger.debug('Received instruction: %s' % instruction)
                return instruction

            # We are still waiting for instruction termination.
            # Read more data into the buffer from the socket.
            data = await self.socket.receive_some(BUF_LEN)
            if not data:
                # No data recieved, connection lost?!
                await self.close()
                self.logger.debug(
                    'Failed to receive instruction. Closing.')
                return None

            # Move the offset forward and add the new data to the buffer.
            offset = max(len(self._buffer) - self.delimiter_size + 1, 0)
            self._buffer.extend(data)

    async def send(self, data):
        """
        Send encoded instructions to Guacamole guacd server.
        """
        self.logger.debug('Sending data: %s' % data)
        await self.socket.send_all(data.encode())

    async def read_instruction(self):
        """
        Read and decode instruction.
        """
        self.logger.debug('Reading instruction.')
        return Instruction.load(await self.receive())

    async def send_instruction(self, instruction):
        """
        Send instruction after encoding.
        """
        self.logger.debug('Sending instruction: %s' % str(instruction))
        return await self.send(instruction.encode())

    async def handshake(self, protocol='vnc', width=1024, height=768, dpi=96,
                  audio=None, video=None, image=None, **kwargs):
        """
        Establish connection with Guacamole guacd server via handshake.
        """
        if protocol not in PROTOCOLS:
            self.logger.debug('Invalid protocol: %s' % protocol)
            raise GuacamoleError('Cannot start Handshake. Missing protocol.')

        if audio is None:
            audio = list()

        if video is None:
            video = list()

        if image is None:
            image = list()

        # 1. Send 'select' instruction
        self.logger.debug('Send `select` instruction.')
        await self.send_instruction(Instruction('select', protocol))

        # 2. Receive `args` instruction
        instruction = await self.read_instruction()
        self.logger.debug('Expecting `args` instruction, received: %s'
                          % str(instruction))

        if not instruction:
            await self.close()
            raise GuacamoleError(
                'Cannot establish Handshake. Connection Lost!')

        if instruction.opcode != 'args':
            await self.close()
            raise GuacamoleError(
                'Cannot establish Handshake. Expected opcode `args`, '
                'received `%s` instead.' % instruction.opcode)

        # 3. Respond with size, audio & video support
        self.logger.debug('Send `size` instruction (%s, %s, %s)'
                          % (width, height, dpi))
        await self.send_instruction(Instruction('size', width, height, dpi))

        self.logger.debug('Send `audio` instruction (%s)' % audio)
        await self.send_instruction(Instruction('audio', *audio))

        self.logger.debug('Send `video` instruction (%s)' % video)
        await self.send_instruction(Instruction('video', *video))

        self.logger.debug('Send `image` instruction (%s)' % image)
        await self.send_instruction(Instruction('image', *image))

        # 4. Send `connect` instruction with proper values
        connection_args = [
            kwargs.get(arg.replace('-', '_'), '') for arg in instruction.args
        ]

        self.logger.debug('Send `connect` instruction (%s)' % connection_args)
        await self.send_instruction(Instruction('connect', *connection_args))

        # 5. Receive ``ready`` instruction, with client ID.
        instruction = await self.read_instruction()
        self.logger.debug('Expecting `ready` instruction, received: %s'
                          % str(instruction))

        if instruction.opcode != 'ready':
            self.logger.warning(
                'Expected `ready` instruction, received: %s instead')

        if instruction.args:
            self._id = instruction.args[0]
            self.logger.debug(
                'Established connection with client id: %s' % self.id)

        self.logger.debug('Handshake completed.')
        self.connected = True
