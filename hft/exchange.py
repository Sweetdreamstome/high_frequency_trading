import logging
import time
from twisted.internet.protocol import Protocol, ClientFactory
from twisted.internet import reactor
from collections import deque
from .decorators import timer

log = logging.getLogger(__name__)

class OUCH(Protocol):
    bytes_needed = {
        'S': 10,
        'E': 40,
        'C': 28,
        'U': 80,
        'A': 66,
        'Q': 41,
    }

    def __init__(self):
        super()
        self.buffer = deque()

    def connectionMade(self):
        log.debug('connection made.')
    
    def dataReceived(self, data):
        header = chr(data[0])
        try:
            bytes_needed = self.bytes_needed[header]
        except KeyError:
             raise ValueError('unknown header %s.' % header)

        if len(data) >= bytes_needed:
            remainder = bytes_needed
            self.buffer.extend(data[:remainder])
            data = data[remainder:]
            try:
                self.handle_incoming_data()
            except Exception as e:
                log.exception(e)
            finally:
                self.buffer.clear()

        if len(data):
            self.dataReceived(data)

    def handle_incoming_data(self):
        market_id = self.factory.market
        try:
            self.factory.dispatcher.dispatch('exchange', bytes(self.buffer), 
                subsession_id=self.factory.subsession_id, market_id=market_id)
        except Exception as e:
            log.exception('error processing exchange message (type:%s, market:%s), ignoring..: %s', 
                header, market_id, e)

    def sendMessage(self, msg, delay):
        if not isinstance(msg, bytes):
            msg = msg.tobytes()
        # can receive a message back (accepted),
        # can receive 2 messages (accepted, executed),
        # can receive 0 message (replace dying silently).
        reactor.callLater(delay, self.transport.write, msg)


class OUCHConnectionFactory(ClientFactory):
    protocol = OUCH

    def __init__(self, subsession_id, market_id, addr, dispatcher):
        super()
        self.market = market_id
        self.subsession_id = subsession_id
        self.addr = addr
        self.connection = None
        self.dispatcher = dispatcher

    def buildProtocol(self, addr):
        log.info('connecting to exchange server at %s' % addr)
        self.connection = ClientFactory.buildProtocol(self, addr)
        return self.connection

    def clientConnectionLost(self, connector, reason):
        log.info('lost connection to exchange at %s: %s' % (self.addr, reason))

    def clientConnectionFailed(self, connector, reason):
        log.debug('failed to connect to exchange at %s: %s' % (self.addr, reason))

exchanges = {}

def connect(subsession_id, market_id, host, port, dispatcher, wait_for_connection=False,
        retries=10):
    addr = '{}:{}'.format(host, port)
    if addr not in exchanges:
        factory = OUCHConnectionFactory(subsession_id, market_id, addr, dispatcher)
        exchanges[addr] = factory
        reactor.connectTCP(host, port, factory)
    else:
        if exchanges[addr].market != market_id:
            log.warning('exchange at {} already has a group: {}'.format(addr, exchanges))
        exchanges[addr].market = market_id
    retry_count = 0
    while not exchanges[addr].connection and wait_for_connection:
        log.info('waiting for connection to %s...' % addr)
        time.sleep(0.5)
        retry_count += 1
        if retry_count > retries:
            raise Exception('failed to connect exchange at %s:%s.' % (host, port))
    return exchanges[addr]


def disconnect(market_id, host, port):
    addr = '{}:{}'.format(host, port)
    try:
        conn = exchanges[addr].connection
    except KeyError:
        log.warning('connection at %s not found.', addr)
    else:
        conn.transport.loseConnection()
        del exchanges[addr]

def send_exchange(host, port, message, delay):
    addr = '{}:{}'.format(host, port)
    if addr not in exchanges:
        raise FileNotFoundError('connection at %s not found.', addr)
    conn = exchanges[addr].connection
    conn.sendMessage(message, delay)