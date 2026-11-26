from machine import Pin, PWM
import time
import gc
import sys
import select
import network
import espnow

SERVO_AABEN, SERVO_LUKKET = 1075, 2050  # us

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


SERVO_GPIO = 23
SERVO_FIL = 'laag_us.txt'


class Servo:

    def __init__(self, aaben, lukket):
        self.lukket = lukket
        self.lav, self.hoej = min(aaben, lukket), max(aaben, lukket)
        Pin(SERVO_GPIO, Pin.OUT, value=0)
        self.pwm = None
        self.holder = False
        try:
            with open(SERVO_FIL) as f:
                us = int(f.read())
        except (OSError, ValueError):
            us = lukket
        if not self.lav <= us <= self.hoej:
            us = lukket
        self.us = self.maal = self.fra = self.gemt = us
        self.t = time.ticks_ms()

    def _gem(self):
        try:
            with open(SERVO_FIL, 'w') as f:
                f.write(str(self.us))
        except OSError:
            pass
        self.gemt = self.us

    def _puls(self):
        d = self.us * 65535 // 20000
        if self.pwm is None:
            self.pwm = PWM(Pin(SERVO_GPIO), freq=50, duty_u16=d)  # duty fra start, ellers 50 % puls
        else:
            self.pwm.duty_u16(d)
        self.holder = True

    def flyt(self, us):
        us = max(self.lav, min(self.hoej, us))
        if us != self.maal:
            self.maal, self.fra = us, self.us

    def stop(self):
        self.maal = self.us
        self._gem()

    def bevaeger(self):
        return self.us != self.maal

    def er(self, us):
        return self.us == us == self.maal

    def tik(self, nu):
        if self.us == self.maal or time.ticks_diff(nu, self.t) < 0:
            return
        self.t = time.ticks_add(nu, 20)
        if not self.holder:
            self._puls()
            return
        rest = abs(self.maal - self.us)
        trin = min(rest, 2 if rest <= 100 or abs(self.us - self.fra) < 100 else 7)
        self.us += trin if self.maal > self.us else -trin
        self._puls()
        if self.us == self.maal or abs(self.us - self.gemt) >= 50:
            self._gem()
        if self.us == self.maal == self.lukket:  # lukket: slip
            self.pwm.duty_u16(0)
            self.holder = False

    def sluk(self):
        self.flyt(self.lukket)
        while self.bevaeger():
            self.tik(time.ticks_ms())
            time.sleep_ms(5)
        if self.pwm is not None:
            self.pwm.deinit()
        Pin(SERVO_GPIO, Pin.OUT, value=0)


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
    net = Net('B')
    hall = Indgang(4, 200, 1000)
    kontakt = Indgang(13, 50, 300)
    laag = Servo(SERVO_AABEN, SERVO_LUKKET)
    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)
    bil = hall.v == 0
    tur = None
    pak = False
    linje = ''
    if laag.us != SERVO_LUKKET:
        print('# ADVARSEL: laaget stod ved %d us, ikke lukket' % laag.us)
    print('# Base klar')
    net.send('R', 'HALL', int(bil))

    def kommando(k, tid, a):
        nonlocal tur, pak
        if k == 'ORDER':
            if tur == tid:  # samme ordre igen
                return None
            if tur:
                return 'BUSY'
            if a not in ('1', '2'):
                return 'BAD'
            if not bil:
                return 'NOT_HOME'
            if kontakt.v:
                return 'LID_OPEN'
            if not net.send('R', 'BESTIL', a, vigtig=True):
                return 'NO_ROVER'
            tur, pak = tid, True
            laag.flyt(SERVO_AABEN)
        elif k == 'LUK' and tur in (None, tid):  # ogsaa uden aktiv tur
            laag.flyt(SERVO_LUKKET)
            net.send('R', 'LUK', vigtig=True)
            tur, pak = None, False
        elif tid != tur:
            return 'WRONG_TRIP'
        elif k == 'KLAR' and pak:
            if not net.send('R', 'KLAR', vigtig=True):
                return 'NO_ROVER'
            laag.flyt(SERVO_LUKKET)
            pak = False
        elif k == 'STOP':
            laag.stop()
            pak = False
            if not net.send('R', 'STOP', vigtig=True):
                return 'NO_ROVER'
        elif k == 'FORTSAET':
            if not net.send('R', 'FORTSAET', vigtig=True):
                return 'NO_ROVER'
        else:
            return 'BAD'

    try:
        while True:
            nu = time.ticks_ms()
            b = hall.opdater(nu) == 0
            if b != bil:
                bil = b
                net.send('R', 'HALL', int(b))
            for fra, typ, d in net.modtag():
                if typ == 'HEJ':
                    print('# %s har meldt sig' % fra)
                if fra != 'R':
                    continue
                if typ == 'EV':
                    print(','.join([d[0], tur or '-'] + d[1:]))  # med turens id
                    if d[0] == 'HOME':
                        tur = None
                elif typ == 'TEMP':
                    print('TEMP,rover,' + ','.join(d))
                elif typ == 'ST':
                    print('# BIL: ' + ','.join(d))
                elif typ == 'HALL?':
                    net.send('R', 'HALL', int(bil))
            laag.tik(nu)
            k = kontakt.v
            if kontakt.opdater(nu) != k:
                print('LID,%s,B,%s' % (tur or '-', 'OPEN' if kontakt.v else 'CLOSED'))
            while poll.poll(0):
                c = sys.stdin.read(1)
                if c not in '\r\n':
                    linje += c
                    continue
                d = linje.strip().split(',')
                linje = ''
                if d[0]:
                    tid = d[1] if len(d) > 1 else '-'
                    grund = kommando(d[0].upper(), tid, d[2] if len(d) > 2 else '')
                    print('OK,' + tid if grund is None else 'NAK,%s,%s' % (tid, grund))
            time.sleep_ms(5)
    finally:
        laag.sluk()


main()
