# Contador de 16 bits UP/DOWN — EEL280, Experimento 5

Interface em **Python 3 + PyQt6** que supervisiona um contador de 16 bits rodando em um **Arduino Uno**.
Sem Arduino, a interface roda uma **simulação local completa**.

## 1. Hipóteses adotadas (o PDF foi corrigido pelo professor)

O PDF pede flip-flops JK e portas lógicas. O professor informou que isso **não é necessário**: só o
Arduino e os botões. Por isso:

| # | Hipótese | Onde está |
|---|---|---|
| 1 | O contador é um `uint16_t` no Arduino, atualizado pelo Timer1 (hardware, sem `delay()`). O Python **não conta**: só envia comandos e exibe o que recebe. | `firmware/` |
| 2 | A detecção do valor 10.000 é feita no Arduino (o valor atual é comparado a 10.000 dentro da interrupção, com contador de ocorrências). Não é feita no Python. | `firmware/`, `Snapshot.detect` |
| 3 | Botões físicos: D2 = START/PAUSE, D3 = UP/DOWN, D4 = RESET, D5 = LIMITE 10.000. `INPUT_PULLUP`, **ativos em nível 0**. | `firmware/` |
| 4 | RESET para a contagem (estado PARADO) e vai ao valor inicial do sentido: UP → 0; DOWN → 65.535 (ou 10.000 com limite). | `CounterModel.reset` |
| 5 | Ativar o limite com valor > 10.000 leva ao valor inicial do sentido. | `CounterModel.set_limit` |
| 6 | O estado REINICIALIZANDO é só visual (0,6 s após o RESET). | `main_window.py` |
| 7 | Protocolo serial próprio (115200 baud), não Firmata: precisamos de estado completo a 20 Hz, eventos de botão e período medido. | `comm/protocol.py` |
| 8 | A detecção de 10.000 dura microssegundos, então o Arduino **conta** as ocorrências e a interface segura o LED aceso por 0,45 s. | `main_window._on_state` |
| 9 | O LCD 16x2 é opcional (`USE_LCD` no firmware). Os pinos dele são RS=12, E=11, D4=10, D5=9, D6=8, D7=7. | `firmware/` |

## 2. Arquitetura

```
Botões físicos (D2..D5) ──► Arduino Uno ──USB/Serial 115200──► SerialWorker (QThread, PySerial)
                           Timer1 + uint16                              │
                           detecção 10.000                              ▼
                                                              SerialBackend ─┐
                                                                             ├─► MainWindow (PyQt6)
                                          SimBackend (CounterModel) ─────────┘
```

* **Interface** (`ui/`) só apresenta e envia comandos.
* **Lógica do contador** (`core/`) é pura, sem Qt, e é a base da simulação e dos testes.
* **Comunicação** (`comm/`) roda em thread própria e nunca trava a janela.
* Com o Arduino ativo, **nenhum dado simulado** é gerado. Sem frames, a tela mostra "sem comunicação".

A aba **Arquitetura** do programa mostra os diagramas de blocos e de comunicação, com a cor da seta USB
acompanhando o estado real da conexão.

## 3. Lógica de contagem

| Modo | Sequência |
|---|---|
| UP, faixa completa | 0 → 65.535 → 0 … (65.536 estados) |
| DOWN, faixa completa | 65.535 → 0 → 65.535 … |
| UP, limitado | 0 → 10.000 → 0 … (10.001 estados) |
| DOWN, limitado | 10.000 → 0 → 10.000 … |
| PAUSE | congela, preserva o valor |

### Temporização (ciclo de 20 s)

O Timer1 (16 MHz, prescaler 1, modo CTC) só gera períodos inteiros de 62,5 ns:

| Faixa | Frequência ideal | Ciclos/passo | OCR1A | Frequência real | Ciclo real | Erro |
|---|---|---|---|---|---|---|
| 0…65.535 | 65.536/20 = 3.276,8 Hz | 4.883 | 4.882 | 3.276,67 Hz | 20,0008 s | +0,004 % |
| 0…10.000 | 10.001/20 = 500,05 Hz | 31.997 | 31.996 | 500,047 Hz | 20,0001 s | +0,0006 % |

O erro teórico de arredondamento é desprezível. O erro **medido** depende do cristal do Arduino, e o
Arduino mede o período de cada ciclo com `micros()` e envia no frame `C,...`. A interface mostra o
período medido, o erro relativo e a frequência medida, e guarda no histórico. A interface atualiza a
~20 quadros/s, mesmo com o contador girando a 3,3 kHz.

## 4. Estrutura de arquivos

```
contador16/
├── main.py                      ponto de entrada (python main.py)
├── requirements.txt             PyQt6, pyserial
├── build_windows.bat            gera o .exe com PyInstaller
├── firmware/contador16/contador16.ino   código do Arduino
├── contador/
│   ├── core/
│   │   ├── counter_model.py     lógica do contador 16 bits (UP/DOWN, limite, reset), sem Qt
│   │   └── timing.py            cálculos do Timer1, frequências, erro relativo
│   ├── comm/
│   │   ├── protocol.py          formato das mensagens (parse/encode), sem Qt
│   │   ├── serial_worker.py     QThread com PySerial: leitura, envio, reconexão
│   │   └── backends.py          SimBackend (simulação) e SerialBackend (Arduino)
│   └── ui/
│       ├── theme.py             cores e folha de estilo (QSS)
│       ├── widgets.py           display de bits, LED, medidor circular, cartão
│       ├── charts.py            gráfico da contagem e dos períodos
│       ├── diagrams.py          diagramas de blocos e de comunicação
│       └── main_window.py       janela principal (abas Painel, Gráficos, Histórico, Arquitetura)
└── tests/
    ├── test_counter_model.py    UP, DOWN, START, PAUSE, RESET, limite, sincronismo
    └── test_protocol_timing.py  protocolo serial e temporização de 20 s
```

## 5. Instalação

Requer Python 3.10 ou superior (testado com 3.12).

```bash
cd contador16
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

No Linux, para acessar a porta serial: `sudo usermod -a -G dialout $USER` (depois, sair e entrar).

## 6. Executar

```bash
python main.py
```

* **Simulação local:** abre assim por padrão. Aperte START e acompanhe.
* **Arduino:** mude "Modo" para "Arduino (serial)", escolha a porta e a velocidade (115200) e clique em **Conectar**.

## 7. Conectar e testar o Arduino

**Ligações:** um lado de cada botão no pino e o outro no GND (sem resistor, o código usa `INPUT_PULLUP`).

| Botão | Pino |
|---|---|
| START/PAUSE | D2 |
| UP/DOWN | D3 |
| RESET | D4 |
| LIMITE 10.000 | D5 |

**Passos:**

1. Abra `firmware/contador16/contador16.ino` na Arduino IDE, escolha *Arduino Uno* e a porta, e clique em **Carregar**.
2. Abra o Monitor Serial a 115200 baud. Deve aparecer `H,CONTADOR16,1` e depois linhas `S,0,1,0,0,0,0` a cada 50 ms. Aperte um botão: aparece `B,...`. **Feche o Monitor Serial** antes de usar o programa em Python (só um programa usa a porta).
3. No programa, escolha a porta e clique em **Conectar**. O chip deve ficar verde (ARDUINO CONECTADO).
4. Rode a lista de verificação abaixo.

### Lista de verificação (UP, DOWN, START, PAUSE, RESET, limite)

| # | Ação | Resultado esperado |
|---|---|---|
| 1 | START (tela ou botão D2) | Estado CONTANDO; valor sobe; os 16 LEDs virtuais acompanham o decimal e o hexadecimal. |
| 2 | Esperar 2 ciclos | Valor passa de 65.535 para 0. O 1º "FIM DE CICLO" não tem medida (o período é medido de um reinício ao próximo); do 2º em diante o histórico mostra período ≈ 20 s e o erro relativo. |
| 3 | PAUSE | Estado PAUSADO; o valor para e **não se perde**; START retoma do mesmo valor. |
| 4 | DOWN | Valor passa a diminuir. Ao chegar em 0 vai para 65.535. |
| 5 | RESET em UP | Chip REINICIALIZANDO, depois PARADO; valor 0; tempo zerado. |
| 6 | RESET em DOWN | Valor 65.535. |
| 7 | LIMITE ligado + UP + START | Conta 0 → 10.000 → 0; medidor chega a 100 % em 10.000; ciclo ≈ 20 s. |
| 8 | LIMITE ligado + DOWN + RESET | Valor inicial 10.000; conta 10.000 → 0 → 10.000. |
| 9 | Passar por 10.000 | O LED "10.000 DETECTADO" acende e o contador de detecções sobe, mesmo na faixa completa. |
| 10 | Apertar cada botão físico | Aparece "(botão físico)" no histórico e a tela acompanha. |
| 11 | Desconectar o cabo USB | Banner vermelho "Conexão perdida"; ao reconectar, a porta reabre sozinha (a cada 2 s). |
| 12 | Aba Histórico → Exportar CSV | Arquivo com data, hora, modo, limite, valor e ação. |

## 8. Testes automáticos (lógica, sem Qt e sem Arduino)

```bash
python -m unittest discover -s tests -t . -v
```

Eles verificam: UP/DOWN com reinício nas duas faixas, START/PAUSE (sem perda de valor), RESET por modo,
limite acima de 10.000, detecção de 10.000, sincronismo decimal/hex/bits, protocolo (frames válidos e
inválidos) e erro de temporização < 0,01 %. O teste mais forte compara o modelo com um passo
unitário escrito como a interrupção do firmware, em 400 cenários aleatórios.

## 9. Gerar o executável do Windows

No Windows, com o ambiente virtual ativo:

```bat
build_windows.bat
```

O programa fica em `dist\Contador16\Contador16.exe` (copie a pasta `Contador16` inteira). Se a lista de
portas aparecer vazia no `.exe`, confirme que o driver do Arduino (CH340 ou ATmega16U2) está instalado.

## 10. Protocolo serial (resumo)

| Sentido | Mensagem | Significado |
|---|---|---|
| PC → Arduino | `START` `PAUSE` `RESET` `UP` `DOWN` `LIM1` `LIM0` `PING` `STATUS` | Comandos |
| Arduino → PC | `S,valor,up,estado,limite,det,ndet` | Estado, a 20 Hz e a cada mudança |
| Arduino → PC | `B,START\|DIR\|RESET\|LIMIT` | Botão físico acionado |
| Arduino → PC | `C,periodo_us` | Fim de ciclo e período medido (0 = sem medida válida) |
| Arduino → PC | `H,CONTADOR16,1`, `PONG`, `ERR,texto` | Saudação, resposta ao PING, erro |

Se não chegar nenhum frame por 1,5 s, a interface marca "comunicação perdida" e tenta de novo.
