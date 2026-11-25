"""Medirover - BASE (KiCad Base 0.21). Gem som main.py. Sidder paa USB i Ubuntu-serveren.

Serveren skriver een linje pr. kommando (ASCII, komma, LF). <id> er turens UUID:
  ORDER,<id>,<1|2>   bilen skal holde i basen (Hall). Begge laag aabner til pakning.
  KLAR,<id>          pakket: begge laag lukker, og bilen koerer.
  STOP,<id>          bilen stopper, laagene bliver hvor de er. Turen er reserveret til LUK.
  FORTSAET,<id>      bilen proever igen efter en fejl.
  LUK,<id>           afslutter en stoppet tur: begge laag lukker langsomt.
Basen svarer OK,<id> eller NAK,<id>,<grund> og sender bilens haendelser med turens id:
  STARTED ARRIVED HALL LID ACK HOME OBST CLEAR ERR og TEMP,rover,<C>,<%RH>.  "# ..." er til mennesker.
Laaget: start med LUKKET laag, og flyt det aldrig med haanden. SW101 skal vaere taendt.
Ben: Hall GPIO4 (0 = magnet), servo GPIO23.
"""
from machine import Pin, PWM
import time
import gc
import sys
import select
import network
import espnow

SERVO_AABEN, SERVO_LUKKET = 1075, 2050     # laag_finjuster.py 23/11

# ---------- Radio: ESP-NOW (samme kode paa alle fire) ----------
KANAL = 1
BC = b'\xff' * 6


class Net:
    """Besked = tekst 'fra,til,type,data...'. Enhederne laerer hinandens MAC af foerste besked
    (alle siger HEJ ved opstart). Kendt modtager: unicast. vigtig=True venter paa modtagerens
    kvittering og proever op til 4 gange. Ukendt modtager: broadcast (til-feltet filtrerer)."""

    def __init__(self, navn):
        w = network.WLAN(network.STA_IF)
        try:
            w.active(True)
        except OSError:                   # "WiFi Out of Memory": ryd op og proev igen
            gc.collect()
            w.active(True)
        for kw in ({'channel': KANAL}, {'pm': getattr(w, 'PM_NONE', 0)}):   # samme kanal, ingen stroemspar
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
            if self.mac.get(d[0]) != mac:          # ny (eller genstartet) enhed: husk MAC
                try:
                    self.e.add_peer(mac)
                except OSError:
                    pass
                self.mac[d[0]] = mac
                if d[2] == 'HEJ':
                    self.send(d[0], 'HEJ')         # svar, saa den ogsaa kender os
            if d[1] == self.navn or d[1] == '*':
                ud.append((d[0], d[2], d[3:]))


# ---------- Skaansom servo (samme kode paa base og bil) ----------
SERVO_GPIO = 23
SERVO_FIL = 'laag_us.txt'


class Servo:
    """MG90S, skaansomt (gearene er knaekket for mange gange):
    - ingen puls foer foerste bevaegelse, og den starter ved den gemte stilling: intet ryk
    - PWM oprettes med den rigtige pulsbredde (ellers kan ESP32 give 50 % duty et oejeblik)
    - 2 us pr. 20 ms de foerste og sidste 100 us, ellers 5 us pr. 20 ms (ca. 5 s pr. bevaegelse)
    - holder i aaben (laaget maa ikke falde), slipper i lukket (presser ikke)
    - aldrig uden for aaben..lukket. Stillingen gemmes for hver 50 us og ved stop
    Bevaegelsen sker i tik(), som kaldes tit. Den blokerer ikke."""

    def __init__(self, aaben, lukket):
        self.aaben, self.lukket = aaben, lukket
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
            self.pwm = PWM(Pin(SERVO_GPIO), freq=50, duty_u16=d)
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
            self._puls()                          # griber ved den kendte stilling
            return
        rest = abs(self.maal - self.us)
        trin = min(rest, 2 if rest <= 100 or abs(self.us - self.fra) < 100 else 5)
        self.us += trin if self.maal > self.us else -trin
        self._puls()
        if self.us == self.maal or abs(self.us - self.gemt) >= 50:
            self._gem()
        if self.us == self.maal == self.lukket:
            self.pwm.duty_u16(0)                  # laaget hviler: slip
            self.holder = False

    def sluk(self):
        """Programmet stopper: luk langsomt foerst, saa laaget ikke falder."""
        self.flyt(self.lukket)
        while self.bevaeger():
            self.tik(time.ticks_ms())
            time.sleep_ms(5)
        if self.pwm is not None:
            self.pwm.deinit()
        Pin(SERVO_GPIO, Pin.OUT, value=0)


class Indgang:
    """Afprellet indgang: skifter foerst, naar ny vaerdi har vaeret stabil i ms[ny vaerdi]."""

    def __init__(self, gpio, ms0, ms1):
        self.p = Pin(gpio, Pin.IN)                # eksterne modstande paa printet
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
    laag = Servo(SERVO_AABEN, SERVO_LUKKET)
    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)
    bil = hall.v == 0                     # Hall ser bilen i basen
    tur = None                            # turens id fra ORDER til HOME eller LUK
    pak = False                           # bestilt, men ikke pakket endnu
    linje = ''
    if laag.us != SERVO_LUKKET:
        print('# ADVARSEL: laaget stod ved %d us, ikke lukket' % laag.us)
    print('# Base klar')
    net.send('R', 'HALL', int(bil))

    def kommando(k, tid, a):
        """Udfoer een kommando fra serveren. Returnerer None (OK) eller grunden til NAK."""
        nonlocal tur, pak
        if k == 'ORDER':
            if tur == tid:
                return None                   # samme bestilling sendt igen
            if tur:
                return 'BUSY'
            if a not in ('1', '2'):
                return 'BAD'
            if not bil:
                return 'NOT_HOME'
            if not net.send('R', 'BESTIL', a, vigtig=True):
                return 'NO_ROVER'
            tur, pak = tid, True
            laag.flyt(SERVO_AABEN)
        elif k == 'LUK' and tur in (None, tid):
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
                if typ == 'EV':                    # bilens haendelse, med turens id
                    print(','.join([d[0], tur or '-'] + d[1:]))
                    if d[0] == 'HOME':
                        tur = None
                elif typ == 'TEMP':
                    print('TEMP,rover,' + ','.join(d))
                elif typ == 'ST':
                    print('# BIL: ' + ','.join(d))
                elif typ == 'HALL?':
                    net.send('R', 'HALL', int(bil))
            laag.tik(nu)
            while poll.poll(0):                    # serverens linje, et tegn ad gangen
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
