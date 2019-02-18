from .trader import BCSTrader
from .orderstore import OrderStore
from .utility import format_message
from collections import deque


class InvestorFactory:
    @staticmethod
    def get_investor(session_format, *args, **kwargs):
        return ELOInvestor(*args, **kwargs)


class ELOInvestor(BCSTrader):

    message_dispatch = { 'A': 'accepted', 'investor_arrivals': 'invest',
        'E': 'executed', 'C': 'canceled'}

    def __init__(self, market_id, exchange_host, exchange_port):
        self.id = 0
        self.market_id = market_id
        self.exchange_host = exchange_host
        self.exchange_port = exchange_port
        self.orderstore = OrderStore(0, market_id)
        self.outgoing_messages = deque()

    def invest(self, **kwargs):
        order_info = self.orderstore.enter(**kwargs)
        message_content = {'host': self.exchange_host, 'port': self.exchange_port, 
            'type': 'enter', 'delay':0., 'order_info': order_info}
        internal_message = format_message('exchange', **message_content)
        self.outgoing_messages.append(internal_message)
    
    def accepted(self, **kwargs):
        super().accepted(**kwargs)

    def executed(self, **kwargs):
        order_info =  self.orderstore.confirm('executed', **kwargs)
        buy_sell_indicator = order_info['buy_sell_indicator']
        price = order_info['price']
        order_token = kwargs['order_token']
        message_content = { 'type': 'executed', 'price': price, 
            'order_token': order_token, 'endowment': 0,
            'inventory': self.orderstore.inventory}
        self.broadcast(**message_content)
        return order_info