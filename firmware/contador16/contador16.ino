// Contador UP/DOWN de 16 bits - Arduino Uno
// EEL280 - Experimento 5 (versao sem flip-flops, autorizada pelo professor)
//
// O Arduino guarda e atualiza a contagem (uint16_t) com o Timer1 em hardware.
// O Python (PyQt6) apenas supervisiona: envia comandos e exibe o estado recebido.
//
// Botoes (INPUT_PULLUP -> ATIVOS EM NIVEL 0; um lado no pino, outro no GND):
//   D2 = START/PAUSE    D3 = UP/DOWN    D4 = RESET    D5 = LIMITE 10.000
//
// Protocolo serial 115200 baud (ver contador/comm/protocol.py):
//   PC -> Arduino: START PAUSE RESET UP DOWN LIM1 LIM0 PING STATUS
//   Arduino -> PC: H,CONTADOR16,1 | PONG | S,valor,up,estado,limite,det,ndet
//                  B,botao | C,periodo_us | ERR,texto
//
// LCD 16x2 e opcional: mude USE_LCD para 1 (pinos RS=12 E=11 D4=10 D5=9 D6=8 D7=7).

#include <Arduino.h>
#include <string.h>

#define USE_LCD 0
#if USE_LCD
#include <LiquidCrystal.h>
LiquidCrystal lcd(12, 11, 10, 9, 8, 7);
#endif

// ---------- Pinos ----------
const uint8_t PIN_START = 2;
const uint8_t PIN_DIR   = 3;
const uint8_t PIN_RESET = 4;
const uint8_t PIN_LIMIT = 5;

// ---------- Temporizacao (Timer1, CTC, prescaler 1, 16 MHz) ----------
// Faixa completa: 65.536 estados / 20 s = 3276,8 Hz -> 16e6/3276,8 = 4882,8 ciclos
//   arredondado para 4883 ciclos por passo -> OCR1A = 4882 -> 3276,67 Hz
//   ciclo completo = 65536 * 4883 / 16e6 = 20,0008 s (erro +0,004 %)
// Faixa 0..10000: 10.001 estados / 20 s = 500,05 Hz -> 16e6/500,05 = 31996,8 ciclos
//   arredondado para 31997 ciclos por passo -> OCR1A = 31996 -> 500,047 Hz
//   ciclo completo = 10001 * 31997 / 16e6 = 20,0001 s (erro +0,0006 %)
const uint16_t OCR_FULL  = 4882;
const uint16_t OCR_LIMIT = 31996;
const uint16_t LIMITE    = 10000;
const uint32_t BAUD      = 115200;

enum : uint8_t { ST_STOPPED = 0, ST_RUNNING = 1, ST_PAUSED = 2 };

// ---------- Estado (compartilhado com a ISR) ----------
volatile uint16_t count = 0;
volatile uint16_t detections = 0;      // vezes que 10.000 foi atingido desde o RESET
volatile uint8_t  state = ST_STOPPED;
volatile bool up = true;
volatile bool limitOn = false;
volatile bool wrapped = false;
volatile bool periodValid = false;
volatile uint32_t lastWrap = 0;
volatile uint32_t periodUs = 0;

ISR(TIMER1_COMPA_vect) {
  if (state != ST_RUNNING) return;
  bool wrap = false;
  if (up) {
    if (limitOn) {
      if (count >= LIMITE) { count = 0; wrap = true; } else count++;
    } else {
      if (count == 0xFFFF) wrap = true;
      count++;                                   // 65535 + 1 volta a 0 (uint16_t)
    }
  } else {
    if (count == 0) {
      wrap = true;
      count = limitOn ? LIMITE : 0xFFFF;
    } else count--;
  }
  if (count == LIMITE) detections++;             // deteccao do valor 10.000
  if (wrap) {
    uint32_t t = micros();
    periodUs = periodValid ? (t - lastWrap) : 0;
    lastWrap = t;
    periodValid = true;
    wrapped = true;
  }
}

uint16_t initialValue() {
  return up ? 0 : (limitOn ? LIMITE : 0xFFFF);
}

void setTimer() {
  noInterrupts();
  TCCR1A = 0;
  TCCR1B = _BV(WGM12) | _BV(CS10);               // CTC, prescaler 1
  OCR1A  = limitOn ? OCR_LIMIT : OCR_FULL;
  TCNT1  = 0;
  TIMSK1 = _BV(OCIE1A);
  interrupts();
}

// ---------- Acoes (usadas pelos botoes e pelos comandos seriais) ----------
void doStart()  { state = ST_RUNNING; periodValid = false; }
void doPause()  { if (state == ST_RUNNING) { state = ST_PAUSED; periodValid = false; } }
void doReset()  {
  noInterrupts();
  state = ST_STOPPED;
  count = initialValue();
  detections = 0;
  periodValid = false;
  interrupts();
}
void doSetDir(bool u) { up = u; periodValid = false; }
void doSetLimit(bool on) {
  noInterrupts();
  limitOn = on;
  if (on && count > LIMITE) count = initialValue();
  periodValid = false;
  interrupts();
  setTimer();                                    // troca a frequencia do clock
}

void sendState() {
  uint16_t c, d; uint8_t s; bool u, l;
  noInterrupts(); c = count; d = detections; s = state; u = up; l = limitOn; interrupts();
  Serial.print(F("S,"));  Serial.print(c);
  Serial.print(',');      Serial.print(u ? 1 : 0);
  Serial.print(',');      Serial.print(s);
  Serial.print(',');      Serial.print(l ? 1 : 0);
  Serial.print(',');      Serial.print(c == LIMITE ? 1 : 0);
  Serial.print(',');      Serial.println(d);
}

// ---------- Botoes com debounce ----------
struct Btn { uint8_t pin; bool last; uint32_t t; };
Btn bStart = {PIN_START, HIGH, 0};
Btn bDir   = {PIN_DIR,   HIGH, 0};
Btn bReset = {PIN_RESET, HIGH, 0};
Btn bLimit = {PIN_LIMIT, HIGH, 0};

bool pressed(Btn &b) {
  bool r = digitalRead(b.pin);
  if (r != b.last && millis() - b.t > 30) {
    b.t = millis();
    b.last = r;
    if (r == LOW) return true;                   // borda de descida = pressionou
  }
  return false;
}

// ---------- Comandos seriais ----------
void handleCommand(const char *c) {
  if      (!strcmp(c, "START"))  { doStart(); }
  else if (!strcmp(c, "PAUSE"))  { doPause(); }
  else if (!strcmp(c, "RESET"))  { doReset(); }
  else if (!strcmp(c, "UP"))     { doSetDir(true); }
  else if (!strcmp(c, "DOWN"))   { doSetDir(false); }
  else if (!strcmp(c, "LIM1"))   { doSetLimit(true); }
  else if (!strcmp(c, "LIM0"))   { doSetLimit(false); }
  else if (!strcmp(c, "STATUS")) { /* apenas responde abaixo */ }
  else if (!strcmp(c, "PING"))   { Serial.println(F("PONG")); return; }
  else { Serial.print(F("ERR,")); Serial.println(c); return; }
  sendState();
}

void readSerial() {
  static char buf[16];
  static uint8_t n = 0;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      buf[n] = 0;
      if (n > 0) handleCommand(buf);
      n = 0;
    } else if (n < sizeof(buf) - 1) {
      buf[n++] = ch;
    } else {
      n = 0;                                     // linha longa demais: descarta
    }
  }
}

#if USE_LCD
void showLcd(uint16_t v) {
  char l0[17], l1[17];
  snprintf(l0, sizeof(l0), "%5u %04X  %c%c%c", v, v,
           up ? 'U' : 'D', state == ST_RUNNING ? '>' : 'P', limitOn ? 'L' : ' ');
  for (int i = 15; i >= 0; i--) l1[15 - i] = ((v >> i) & 1) ? '1' : '0';
  l1[16] = 0;
  lcd.setCursor(0, 0); lcd.print(l0);
  lcd.setCursor(0, 1); lcd.print(l1);
}
#endif

void setup() {
  pinMode(PIN_START, INPUT_PULLUP);
  pinMode(PIN_DIR,   INPUT_PULLUP);
  pinMode(PIN_RESET, INPUT_PULLUP);
  pinMode(PIN_LIMIT, INPUT_PULLUP);
#if USE_LCD
  lcd.begin(16, 2);
#endif
  Serial.begin(BAUD);
  Serial.println(F("H,CONTADOR16,1"));
  setTimer();
}

uint32_t tTx = 0, tLcd = 0;

void loop() {
  readSerial();

  if (pressed(bStart)) {                         // START/PAUSE
    if (state == ST_RUNNING) doPause(); else doStart();
    Serial.println(F("B,START")); sendState();
  }
  if (pressed(bDir)) {                           // UP/DOWN
    doSetDir(!up);
    Serial.println(F("B,DIR")); sendState();
  }
  if (pressed(bReset)) {                         // RESET
    doReset();
    Serial.println(F("B,RESET")); sendState();
  }
  if (pressed(bLimit)) {                         // LIMITE 10.000
    doSetLimit(!limitOn);
    Serial.println(F("B,LIMIT")); sendState();
  }

  if (wrapped) {                                 // fim de ciclo (periodo medido)
    uint32_t p;
    noInterrupts(); wrapped = false; p = periodUs; interrupts();
    Serial.print(F("C,")); Serial.println(p);
  }

  uint32_t now = millis();
  if (now - tTx >= 50) {                         // estado a 20 Hz
    tTx = now;
    sendState();
  }
#if USE_LCD
  if (now - tLcd >= 100) {
    tLcd = now;
    uint16_t v; noInterrupts(); v = count; interrupts();
    showLcd(v);
  }
#endif
}
