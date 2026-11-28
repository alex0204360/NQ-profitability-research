"""Streaming episode attribution on synchronized, completed closes."""
class Transfer:
    def __init__(self):
        self.anchor = self.live = self.time = None

    def step(self, tick, micro, peer, basis, prior_verified=True):
        prices=(micro, peer)
        if self.time is None or tick!=self.time+1:
            self.live=self.anchor=None
        self.time=tick
        if basis is None:
            self.live=self.anchor=None
            return None
        raw=peer-micro
        event=self.live
        if event is not None and tick-event['opened']>30:
            self.live=self.anchor=event=None
        if event is not None:
            lead, side=event['leader'],event['direction']
            lag=1-lead
            distance=event['orientation']*(raw-event['basis'])
            if distance>event['peak_gap']:
                event.update(peak=prices, peak_gap=distance, peak_time=tick)
            if distance>0.25:
                return None
            catch=side*(prices[lag]-event['peak'][lag])
            withdraw=side*(event['peak'][lead]-prices[lead])
            closed=event['peak_gap']-distance
            if abs(catch+withdraw-closed)>1e-9:
                raise ArithmeticError('closure attribution inconsistent with observed prices')
            q=max(-1.,min(1.,(catch-withdraw)/closed))
            action=side if q>=.5 else -side if q<=-.5 else 0
            result=dict(**event, resolved=tick, catch=catch, withdraw=withdraw, closed=closed,
                        q=q,action=action,midpoint_change=(sum(prices)-sum(event['anchor_prices']))/2)
            self.live=self.anchor=None
            if abs(raw-basis)<=.25:
                self.anchor=(tick,prices)
            return result
        if abs(raw-basis)<=.25:
            self.anchor=(tick,prices)
            return None
        if self.anchor is None or abs(raw-basis)<1. or not prior_verified:
            return None
        start, old=self.anchor
        self.anchor=None
        if tick-start>30:
            return None
        moves=(micro-old[0],peer-old[1])
        if abs(moves[0])==abs(moves[1]):
            return None
        lead=int(abs(moves[1])>abs(moves[0]))
        side=1 if moves[lead]>0 else -1
        orientation=side*(1 if lead==1 else -1)
        distance=orientation*(raw-basis)
        if distance<1.:
            return None
        self.live=dict(anchor_time=start, anchor_prices=old, opened=tick, leader=lead, direction=side,
                       orientation=orientation, basis=basis, peak=prices, peak_gap=distance, peak_time=tick)
        return None
