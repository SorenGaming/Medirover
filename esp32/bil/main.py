from machine import Pin, PWM, time_pulse_us
import time
import gc
import network
import espnow
import dht
from neopixel import NeoPixel

SERVO_AABEN, SERVO_LUKKET = 1030, 2005
PPC = 26.7
IR_AKSEL = 21

MIN_V, MIN_H = 22.6, 24.6
KF_V, KF_H = 0.0506, 0.0581
KP, KI = 0.0358, 0.061
LKP, LKD = 0.25, 0.06
DREJ90_MAKS, DREJ180_MAKS = 36, 67

FART, DREJFART, KRYBFART = 350, 160, 120
I_MAKS, LMAKS = 40, 0.5
BREMSE_MS = 150
BOOST_RATE, BOOST_MAKS = 40, 30
BAK, LIGEUD, KRYB, TABT = 10, 5, 4, 6
MARK_VINDUE, MARK_PAUSE, MARK_PAUSE_DREJ = 2, 4, 12
HVID_MIN = 0.4
RET_CM, SOEG_CM = 8, 10
DREJ_MIN_180, DREJ_MIN_90 = 0.54, 0.42
START_FART, LMAKS_START = 0.6, 0.8
FORHINDRING, FRI, FRI_MS = 15, 20, 1000
FORHINDRING_STOP, FRI_STOP = 6, 8
RUTER = {'B1': 'VS', 'B2': 'LHS', '1B': 'HS', '2B': 'VLS'}
NEO_LYS = 30
FARVER = {'klar': (0, 0, 255), 'pak': (0, 200, 200), 'koer': (0, 255, 0),
          'forhindring': (255, 90, 0), 'hall': (255, 200, 0), 'venter': (160, 0, 255),
          'fejl': (255, 0, 0), 'faerdig': (255, 255, 255)}

KANAL = 1
BC = b'\xff' * 6


class Net:
    """ESP-NOW: broadcast til modtageren har sagt HEJ, derefter unicast med kvittering."""

    def __init__(self, navn):
        w = network.WLAN(network.STA_IF)
        try:
            w.active(True)
        except OSError:
            gc.collect()
            w.active(True)
        for kw in ({'channel': KANAL}, {'pm': getattr(w, 'PM_NONE', 0)}):
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
    """Skaansom servo: smaa trin naer enderne, slippes i lukket stilling."""

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
            self._puls()
            return
        rest = abs(self.maal - self.us)
        trin = min(rest, 2 if rest <= 100 or abs(self.us - self.fra) < 100 else 7)
        self.us += trin if self.maal > self.us else -trin
        self._puls()
        if self.us == self.maal or abs(self.us - self.gemt) >= 50:
            self._gem()
        if self.us == self.maal == self.lukket:
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


class Fejl(Exception):
    def __init__(self, tekst, kode):
        super().__init__(tekst)
        self.kode = kode


class Afbrudt(Exception):
    pass


class Hjul:
    """Et hjul: PI-regulering af pulser/s med feedforward."""

    def __init__(self, in1, in2, enc, omvendt, d0, kf):
        self.a = PWM(Pin(in1), freq=1000, duty_u16=0)
        self.b = PWM(Pin(in2), freq=1000, duty_u16=0)
        self.omv = omvendt
        self.d0, self.kf = d0, kf
        self.n = self.sidst = self.maal = 0
        self.pps = self.i = self.boost = 0.0
        self.bremse_til = time.ticks_ms()
        self.enc = Pin(enc, Pin.IN)
        self.enc.irq(trigger=Pin.IRQ_RISING, handler=self._puls)

    def _puls(self, p):
        self.n += 1

    def saet(self, pps):
        if pps == 0 or (pps > 0) != (self.maal > 0):
            self.i = 0.0
        self.maal = pps

    def reguler(self, dt):
        n = self.n
        self.pps += ((n - self.sidst) * 1000 / dt - self.pps) * 0.4
        self.sidst = n
        if self.maal == 0:
            self.i = self.boost = 0.0
            if time.ticks_diff(self.bremse_til, time.ticks_ms()) <= 0:
                self._pwm(0)
            return
        m = abs(self.maal)
        fejl = m - self.pps
        if abs(fejl) < 0.3 * m:
            self.i = max(-I_MAKS, min(I_MAKS, self.i + KI * fejl * dt / 1000))
        if self.pps < 0.15 * m:
            self.boost = min(BOOST_MAKS, self.boost + BOOST_RATE * dt / 1000)
        else:
            self.boost = max(0.0, self.boost - 3 * BOOST_RATE * dt / 1000)
        duty = max(0.0, min(100.0, self.d0 + self.kf * m + KP * fejl + self.i + self.boost))
        self._pwm(duty if self.maal > 0 else -duty)

    def _pwm(self, p):
        if self.omv:
            p = -p
        d = int(min(100, abs(p)) * 655)
        self.a.duty_u16(d if p > 0 else 0)
        self.b.duty_u16(d if p < 0 else 0)

    def stop(self):
        """Bremser med begge indgange hoeje i BREMSE_MS."""
        if self.maal != 0 or self.pps > 20:
            self.a.duty_u16(65535)
            self.b.duty_u16(65535)
            self.bremse_til = time.ticks_add(time.ticks_ms(), BREMSE_MS)
        elif time.ticks_diff(self.bremse_til, time.ticks_ms()) <= 0:
            self._pwm(0)
        self.maal = 0
        self.i = 0.0


class Bil:
    def __init__(self):
        self.V = Hjul(16, 17, 33, False, MIN_V, KF_V)
        self.H = Hjul(26, 27, 35, True, MIN_H, KF_H)
        self.irp = [Pin(g, Pin.IN) for g in (39, 34, 36)]
        self.usp = [(Pin(21, Pin.OUT, value=0), Pin(22, Pin.IN)), (Pin(4, Pin.OUT, value=0), Pin(19, Pin.IN))]
        self.usi = 0
        self.taet = [0, 0]
        self.us_cm = [999, 999]
        self.us_til = False
        self.graense, self.fri = FORHINDRING, FRI
        self.np = NeoPixel(Pin(18), 24)
        self.dht = dht.DHT11(Pin(14))
        self.net = Net('R')
        self.laag = Servo(SERVO_AABEN, SERVO_LUKKET)
        self.kontakt = Pin(13, Pin.IN)
        nu = time.ticks_ms()
        self.t_reg = self.t_us = self.t_neo = self.sidst_taet = self.t_kontakt = nu
        self.t_temp = time.ticks_add(nu, -30000)
        self.lys = 'klar'
        self.hall = {}
        self.kvit = None
        self.bestil = None
        self.station = None
        self.klar = self.fortsaet = self.afbryd = self.koerer = False
        self.rute = ''

    def st(self, tekst):
        print('BIL:', tekst)
        self.net.send('B', 'ST', tekst)

    def ev(self, *d):
        self.net.send('B', 'EV', *d)

    def ir(self):
        return tuple(p.value() == 0 for p in self.irp)

    def afstand(self):
        return (self.V.n + self.H.n) / 2

    def stille(self):
        return self.V.pps < 20 and self.H.pps < 20

    def stop_motorer(self):
        self.V.stop()
        self.H.stop()

    def tik(self, afbryd=True):
        """Hovedloekken: radio, regulering, servo, ultralyd, LED og temperatur."""
        nu = time.ticks_ms()
        for fra, typ, d in self.net.modtag():
            self.besked(fra, typ, d)
        dt = time.ticks_diff(nu, self.t_reg)
        if dt >= 20:
            self.t_reg = nu
            self.V.reguler(dt)
            self.H.reguler(dt)
        self.laag.tik(nu)
        if self.us_til and time.ticks_diff(nu, self.t_us) >= 60:
            self.t_us = nu
            self.ultralyd()
        if time.ticks_diff(nu, self.t_neo) >= 300:
            self.t_neo = nu
            f = FARVER[self.lys]
            if self.lys in ('venter', 'fejl') and nu // 300 % 2:
                f = (0, 0, 0)
            self.np.fill(tuple(c * NEO_LYS // 255 for c in f))
            self.np.write()
        if self.V.maal == self.H.maal == 0 and time.ticks_diff(nu, self.t_temp) >= 30000:
            self.temp()
        if afbryd and self.afbryd:
            raise Afbrudt()

    def vent(self, ms, betingelse=None, afbryd=True):
        slut = time.ticks_add(time.ticks_ms(), ms)
        while time.ticks_diff(slut, time.ticks_ms()) > 0:
            self.tik(afbryd)
            if betingelse and betingelse():
                return True
            time.sleep_ms(2)
        return bool(betingelse and betingelse())

    def vent_paa(self, betingelse, afbryd=True):
        while not betingelse():
            self.tik(afbryd)
            time.sleep_ms(2)

    def besked(self, fra, typ, d):
        if typ == 'HALL':
            self.hall[fra] = d[0] == '1'
        elif typ == 'KVIT':
            self.kvit = fra
        elif fra != 'B':
            pass
        elif typ == 'BESTIL':
            if not self.koerer:
                self.bestil = d[0]
            elif d[0] != self.station:
                self.ev('ERR', 'BUSY')
        elif typ == 'KLAR':
            self.klar = True
        elif typ == 'STOP':
            self.afbryd = self.koerer
            self.stop_motorer()
            self.laag.stop()
        elif typ == 'FORTSAET':
            self.fortsaet = True
        elif typ == 'LUK' and not self.koerer:
            self.laag.flyt(SERVO_LUKKET)

    def ultralyd(self):
        trig, echo = self.usp[self.usi]
        if not echo.value():
            trig.value(1)
            time.sleep_us(10)
            trig.value(0)
            t = time_pulse_us(echo, 1, 3000)
            cm = t / 58 if t > 0 else 999
            self.us_cm[self.usi] = cm
            self.taet[self.usi] = self.taet[self.usi] + 1 if cm < self.graense else 0
            if cm < self.fri:
                self.sidst_taet = time.ticks_ms()
        self.usi ^= 1

    def temp(self):
        self.t_temp = time.ticks_ms()
        try:
            self.dht.measure()
            self.net.send('B', 'TEMP', self.dht.temperature(), self.dht.humidity())
        except OSError:
            pass

    def laag_til(self, us, navn):
        self.laag.flyt(us)
        self.vent_paa(lambda: not self.laag.bevaeger())
        self.t_kontakt = time.ticks_ms()
        self.ev('LID', 'R', navn)

    def sikkerhed(self, frem):
        """Krav 2 og 3: koer kun med lukket laag, og stop for forhindringer."""
        if frem and not self.us_til:
            self.taet = [0, 0]
        self.us_til = frem
        if not self.laag.er(SERVO_LUKKET):
            self.stop_motorer()
            self.laag_til(SERVO_LUKKET, 'CLOSED')
        if self.kontakt.value() == 0:
            self.t_kontakt = time.ticks_ms()
        elif time.ticks_diff(time.ticks_ms(), self.t_kontakt) > 300:
            raise Fejl('laagkontakten melder aabent', 'LID')
        if frem and max(self.taet) >= 2:
            self.stop_motorer()
            lys, self.lys = self.lys, 'forhindring'
            self.ev('OBST', int(min(self.us_cm)))
            self.vent_paa(lambda: time.ticks_diff(time.ticks_ms(), self.sidst_taet) >= FRI_MS)
            self.taet = [0, 0]
            self.lys = lys
            self.ev('CLEAR')

    def koer(self, cm, stop=True):
        r = 1 if cm > 0 else -1
        slut = self.afstand() + abs(cm) * PPC
        while self.afstand() < slut:
            self.sikkerhed(r > 0)
            self.V.saet(r * FART)
            self.H.saet(r * FART)
            self.tik()
            time.sleep_ms(1)
        if stop:
            self.stop_motorer()
            self.vent(150)

    def drej(self, retning, maks, min_andel):
        """Drejer til midter-IR har forladt linjen og fundet den naeste."""
        r = -1 if retning == 'V' else 1
        mindst = min_andel * maks * PPC
        start = self.afstand()
        hvid = None
        forladt = False
        while True:
            self.sikkerhed(False)
            self.V.saet(r * DREJFART)
            self.H.saet(-r * DREJFART)
            self.tik()
            c = self.ir()[1]
            d = self.afstand() - start
            if not forladt:
                if c:
                    hvid = None
                elif hvid is None:
                    hvid = d
                elif d - hvid >= HVID_MIN * PPC:
                    forladt = True
            elif c and d >= mindst:
                break
            if d > maks * PPC:
                self.stop_motorer()
                raise Fejl('fandt ikke linjen i drejet', 'TURN')
        self.stop_motorer()
        self.vent(150)
        self.find_linjen(-r, RET_CM)

    def find_linjen(self, r, maks):
        start = self.afstand()
        while not self.ir()[1]:
            if self.afstand() - start > maks * PPC:
                self.stop_motorer()
                return False
            self.V.saet(r * KRYBFART)
            self.H.saet(-r * KRYBFART)
            self.tik()
        self.stop_motorer()
        self.vent(100)
        return True

    def soeg_linjen(self, side):
        self.stop_motorer()
        self.vent(150)
        r = -1 if side < 0 else 1
        if self.find_linjen(r, SOEG_CM) or self.find_linjen(-r, 2 * SOEG_CM):
            self.st('fandt linjen igen')
            return True
        return False

    def foelg(self):
        """Linjefoelger med PD-styring. Udfoerer ruten ved hvert kryds."""
        self.lys = 'koer'
        e_f = side = 0.0
        tabt = None
        sort_v = sort_h = -9999
        sidst = self.afstand()
        pause = MARK_PAUSE_DREJ * PPC
        langsom_til = sidst + MARK_PAUSE_DREJ * PPC
        t = time.ticks_ms()
        vl = vh = FART
        while True:
            self.graense, self.fri = (FORHINDRING_STOP, FRI_STOP) if self.rute[0] == 'S' else (FORHINDRING, FRI)
            self.sikkerhed(True)
            self.tik()
            v, c, h = self.ir()
            d = self.afstand()
            if v:
                sort_v = d
            if h:
                sort_h = d
            if (c and d - sidst >= pause and d - sort_v <= MARK_VINDUE * PPC
                    and d - sort_h <= MARK_VINDUE * PPC):
                a, self.rute = self.rute[0], self.rute[1:]
                self.st('kryds: ' + a)
                if a == 'S':
                    self.stop_motorer()
                    self.vent(200)
                    return
                if a == 'L':
                    self.koer(LIGEUD, False)
                    pause = MARK_PAUSE * PPC
                else:
                    self.koer(IR_AKSEL)
                    self.drej(a, DREJ90_MAKS, DREJ_MIN_90)
                    pause = MARK_PAUSE_DREJ * PPC
                    langsom_til = self.afstand() + MARK_PAUSE_DREJ * PPC
                self.lys = 'koer'
                sidst = self.afstand()
                tabt = None
                sort_v = sort_h = -9999
                e_f = side = 0.0
                continue
            if v or c or h:
                tabt = None
                e = (-0.5 if c else -1.0) if v and not h else (0.5 if c else 1.0) if h and not v else 0.0
                if e:
                    side = e
            else:
                if tabt is None:
                    tabt = d
                elif d - tabt >= TABT * PPC:
                    if not self.soeg_linjen(side):
                        raise Fejl('linjen er vaek - saet bilen paa linjen', 'LINE')
                    tabt = None
                    e_f = 0.0
                    langsom_til = self.afstand() + MARK_PAUSE_DREJ * PPC
                    continue
                e = 2.0 if side > 0 else -2.0 if side < 0 else 0.0
            nu = time.ticks_ms()
            if time.ticks_diff(nu, t) >= 20:
                t = nu
                styr = LKP * e + LKD * (e - e_f) * 10
                e_f = e
                langsom = d < langsom_til
                g = 1.0 if abs(e) >= 2 else (LMAKS_START if langsom else LMAKS)
                styr = max(-g, min(g, styr))
                f = FART * START_FART if langsom else FART
                vl, vh = f * (1 + styr), f * (1 - styr)
            self.V.saet(vl)
            self.H.saet(vh)
            time.sleep_ms(1)

    def hall_ok(self, navn):
        """Krav 3: Hall skal bekraefte, at bilen holder ved det rigtige sted."""
        self.lys = 'hall'
        self.stop_motorer()
        self.net.send(navn, 'HALL?')
        ok = self.vent(3000, lambda: self.hall.get(navn))
        if not ok:
            slut = self.afstand() + KRYB * PPC
            while self.afstand() < slut and not self.hall.get(navn):
                self.sikkerhed(False)
                self.V.saet(KRYBFART)
                self.H.saet(KRYBFART)
                self.tik()
                time.sleep_ms(1)
            self.stop_motorer()
            self.net.send(navn, 'HALL?')
            ok = self.vent(1000, lambda: self.hall.get(navn))
        if any(self.hall.get(n) for n in ('S1', 'S2', 'B') if n != navn):
            raise Fejl('Hall fra forkert sted', 'WRONG_ST')
        if not ok:
            raise Fejl('ingen Hall fra ' + navn, 'NO_HALL')
        if not self.vent(1000, self.stille):
            raise Fejl('bilen staar ikke stille', 'MOVING')
        self.ev('HALL', navn[1] if navn != 'B' else '0')

    def forsoeg(self, fn, *a):
        """Koerer fn igen efter en fejl, naar der trykkes Fortsaet."""
        while True:
            try:
                return fn(*a)
            except Fejl as f:
                self.stop_motorer()
                lys, self.lys = self.lys, 'fejl'
                self.st('FEJL: %s - tryk Fortsaet eller Stop' % f)
                self.ev('ERR', f.kode)
                self.fortsaet = False
                self.vent_paa(lambda: self.fortsaet or self.afbryd, False)
                if self.afbryd:
                    raise Afbrudt()
                self.lys = lys

    def vej(self, noegle):
        if not self.ir()[1]:
            self.st('midter-IR ser ikke linjen ved start')
        self.lys = 'koer'
        self.forsoeg(self.koer, -BAK)
        self.forsoeg(self.drej, 'V', DREJ180_MAKS, DREJ_MIN_180)
        self.rute = RUTER[noegle]
        self.forsoeg(self.foelg)

    def tur(self, st):
        navn = 'S' + st
        self.station = st
        self.lys = 'pak'
        self.klar = False
        self.laag_til(SERVO_AABEN, 'OPEN')
        self.vent_paa(lambda: self.klar)
        self.laag_til(SERVO_LUKKET, 'CLOSED')
        self.ev('STARTED', st)
        self.vej('B' + st)
        self.ev('ARRIVED', st)
        self.forsoeg(self.hall_ok, navn)
        self.temp()
        self.kvit = None
        self.laag_til(SERVO_AABEN, 'OPEN')
        self.net.send(navn, 'AABEN', vigtig=True)
        self.lys = 'venter'
        self.vent_paa(lambda: self.kvit == navn)
        self.ev('ACK', st)
        self.laag_til(SERVO_LUKKET, 'CLOSED')
        self.net.send(navn, 'LUKKET', vigtig=True)
        self.vej(st + 'B')
        self.forsoeg(self.hall_ok, 'B')
        self.temp()
        self.ev('HOME')
        self.lys = 'faerdig'


def main():
    b = Bil()
    try:
        if not b.laag.er(SERVO_LUKKET):
            b.st('ADVARSEL: laaget stod ved %d us, ikke lukket' % b.laag.us)
        b.st('klar')
        while True:
            b.vent_paa(lambda: b.bestil, False)
            b.koerer, b.afbryd = True, False
            try:
                st, b.bestil = b.bestil, None
                b.tur(st)
            except Afbrudt:
                b.lys = 'fejl'
                b.ev('ERR', 'STOPPED')
            b.koerer = b.klar = b.fortsaet = b.afbryd = False
            if b.lys == 'faerdig':
                b.vent(3000, None, False)
                b.lys = 'klar'
    finally:
        b.stop_motorer()
        b.np.fill((0, 0, 0))
        b.np.write()
        b.laag.sluk()


main()
