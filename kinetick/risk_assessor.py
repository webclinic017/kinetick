import os
from datetime import datetime
from math import floor, ceil

from kinetick.bot import Bot
from kinetick.models import Position


class Borg:
    _shared_state = {}

    def __init__(self):
        self.__dict__ = self._shared_state


class RiskAssessor(Borg):
    def __init__(self, initial_capital=1000, max_trades=1, initial_margin=100, risk2reward=1.0, risk_per_trade=100):
        Borg.__init__(self)

        self.capital = initial_capital
        self.initial_capital = initial_capital
        self.max_trades = max_trades
        self.available_margin = initial_margin
        self.initial_margin = initial_margin
        self.risk2reward = risk2reward
        self.risk_per_trade = risk_per_trade
        self.pnl = 0
        self.active_positions = []

        if initial_capital < initial_margin:
            raise Exception("Capital is lower than available_margin")

        Bot().add_command_handler("overview", self.availableMarginHandler, "see available margin")

    def availableMarginHandler(self, update, context):
        update.message.reply_text(f'Available margin: {self.available_margin:.2f} \n '
                                  f'Active Trades: {len(self.active_positions)} \n'
                                  f'Available capital: {self.capital} \n'
                                  f'PNL: {self.pnl} \n')

    @staticmethod
    def get_default_instance():
        return RiskAssessor(initial_capital=6000, max_trades=2, initial_margin=6000, risk2reward=1.3)

    def reset(self):
        self.capital = self.initial_capital
        self.available_margin = self.initial_margin
        self.active_positions.clear()

    def _should_trade(self, entry_price, stop_loss):
        spread = abs(entry_price - stop_loss)
        spread = 5 * round(spread / 5, 2)
        quantity = floor(max(1, int(self.risk_per_trade / spread)))
        margin = quantity * spread
        should_trade = True
        reason = None

        if self.available_margin <= 0:
            should_trade = False
            reason = "Insufficient margin"
        elif margin >= self.available_margin:
            should_trade = False
            reason = "Margin exceeds"
        elif len(self.active_positions) >= self.max_trades:
            should_trade = False
            reason = f'current positions {self.active_positions} exceed max trade limit {self.max_trades}'
        elif (entry_price * quantity) >= self.capital:
            should_trade = False
            reason = f'Insufficient Capital. required: {entry_price * quantity} available: {self.capital}'

        return should_trade, spread, quantity, reason

    def create_position(self, entry_price, stop_loss):
        """
        return trade if all the conditions are met
        :param entry_price:
        :param stop_loss:
        :return: should_trade: Bool, trade: Trade
        """
        should_trade, spread, quantity, reason = self._should_trade(entry_price, stop_loss)
        if not should_trade:
            raise Exception(f'Trade can not be made voids risk margins {reason}')

        direction = "LONG" if stop_loss < entry_price else "SHORT"
        target = 5 * round((spread * self.risk2reward) / 5, 2)
        target = entry_price + target if direction == "LONG" else entry_price - target

        position = Position(quantity=quantity, entry_price=entry_price, target=target,
                            stop=stop_loss, direction=direction)

        return position

    # TODO make thread safe
    def enter_position(self, position):
        if position.entry_time is None:
            position.entry_time = datetime.now()
        should_trade, spread, quantity, reason = self._should_trade(position.entry_price, position.stop)
        if not should_trade:
            raise Exception(f'Trade can not be made void risk margins {reason}')
        self.active_positions.append(position)
        self.available_margin = self.available_margin - spread * quantity
        self.capital = self.capital - (position.entry_price * quantity)
        return position

    # TODO make thread safe
    def exit_position(self, position):
        if position.exit_time is None:
            position.exit_time = datetime.now()
        if position.exit_price is None:
            raise Exception("Trade exit_price is not provided")

        pnl = position.pnl()

        self.available_margin = round(self.available_margin + pnl, 2)
        self.capital = self.capital + pnl
        self.pnl += pnl

        index = self.active_positions.index(position)
        del self.active_positions[index]

        position.realized_pnl = round(pnl * 2, 2) / 2

        return position
