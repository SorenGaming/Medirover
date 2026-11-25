from machine import Pin
import time
import gc
import network
import espnow

NR = 2

KANAL = 1
BC = b'\xff' * 6


class Net:

    def __init__(self, navn):
        w = network.WLAN(network.STA_IF)
        try:
            w.active(True)
        except OSError:
            gc.collect()  # WiFi Out of Memory
            w.active(True)
        for kw in ({'channel': KANAL}, {'pm': getattr(w, 'PM_NONE', 0)}):  # stroemspar taber beskeder
            try:
                w.config(**kw)
            except (OSError, ValueError, AttributeError):
                pass
        self.e = espnow.ESPNow()
        self.e.active(True)
        self.e.add_peer(BC)
        self.navn = navn
        self.mac = {}
        self.send('*', 'HEJ')

    def send(self, til, typ, *data, vigtig=False):
        msg = ','.join((self.navn, til, typ) + tuple(str(d) for d in data))
        mac = self.mac.get(til)
        for _ in range(4 if vigtig else 1):
            try:
                if mac is None:
                    self.e.send(BC, msg, False)
                elif self.e.send(mac, msg, vigtig):
                    return True
            except OSError:
                pass
            if vigtig:
                time.sleep_ms(20)
        return False

    def modtag(self):
        ud = []
        while True:
            mac, msg = self.e.recv(0)
            if msg is None:
                return ud
            try:
                d = msg.decode().split(',')
            except UnicodeError:
                continue
            if len(d) < 3:
                continue
            if self.mac.get(d[0]) != mac:
                try:
                    self.e.add_peer(mac)
                except OSError:
                    pass
                self.mac[d[0]] = mac
                if d[2] == 'HEJ':
                    self.send(d[0], 'HEJ')
            if d[1] == self.navn or d[1] == '*':
                ud.append((d[0], d[2], d[3:]))


class Indgang:

    def __init__(self, gpio, ms0, ms1):
        self.p = Pin(gpio, Pin.IN)
        self.ms = (ms0, ms1)
        self.v = self.k = self.p.value()
        self.t = time.ticks_ms()

    def opdater(self, nu):
        x = self.p.value()
        if x != self.k:
            self.k, self.t = x, nu
        elif x != self.v and time.ticks_diff(nu, self.t) >= self.ms[x]:
            self.v = x
        return self.v


def main():
    net = Net('S%d' % NR)
    hall = Indgang(4, 200, 1000)
    knap = Indgang(13, 30, 30)
    led1 = Pin(22, Pin.OUT, value=0)
    led2 = Pin(21, Pin.OUT, value=0)
    bil = hall.v == 0
    tilst = 'her' if bil else 'tom'
    knap_foer = knap.v
    net.send('R', 'HALL', int(bil))
    print('Station', NR, 'klar:', tilst)
    while True:
        nu = time.ticks_ms()
        b = hall.opdater(nu) == 0
        if b != bil:
            bil = b
            net.send('R', 'HALL', int(b))
            if tilst not in ('venter', 'kvit'):  # laaget er aabent
                tilst = 'her' if b else 'tom'
            print('Hall:', b, '->', tilst)
        for fra, typ, d in net.modtag():
            if fra != 'R':
                continue
            if typ == 'HALL?':
                net.send('R', 'HALL', int(bil))
            elif typ == 'AABEN':
                tilst = 'venter'
                print('laaget er aabent - tryk paa knappen')
            elif typ == 'LUKKET':
                tilst = 'leveret'
        k = knap.opdater(nu)
        tryk = k == 0 and knap_foer == 1
        knap_foer = k
        if tilst == 'venter' and tryk:
            if net.send('R', 'KVIT', vigtig=True):
                tilst = 'kvit'
                print('kvitteret')
            else:
                print('KVIT naaede ikke frem - tryk igen')
        elif tryk:
            print('knap trykket (intet aabent laag)')
        led1.value(tilst in ('her', 'venter', 'kvit'))
        led2.value(tilst in ('kvit', 'leveret') or (tilst == 'venter' and nu // 250 % 2))
        time.sleep_ms(5)


main()
